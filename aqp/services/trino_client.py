"""Trino REST client with structured logging and query history.

Used by the AQP service manager to verify that Trino is not just
reachable on ``/v1/info`` but can actually execute statements against
the configured Iceberg catalog.
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

from aqp.config import settings
from aqp.observability import get_tracer
from aqp.services.trino_probe import probe_trino_coordinator, trino_coordinator_http_url

logger = logging.getLogger(__name__)
_tracer = get_tracer("aqp.services.trino_client")


class TrinoClientError(RuntimeError):
    """Raised when the Trino REST API returns an error or times out."""


@dataclass
class TrinoQueryResult:
    query_id: str | None
    columns: list[str]
    rows: list[list[Any]]
    elapsed_seconds: float
    state: str = "FINISHED"
    error: str | None = None
    statement: str = ""
    statement_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrinoQuerySummary:
    query_id: str
    state: str
    user: str | None
    source: str | None
    catalog: str | None
    schema: str | None
    elapsed_seconds: float | None
    queued_seconds: float | None
    error: str | None
    statement: str
    created: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TrinoVerificationResult:
    coordinator_ok: bool
    coordinator_url: str
    node_id: str | None
    node_version: str | None
    query_ok: bool
    iceberg_catalog_ok: bool
    catalogs: list[str] = field(default_factory=list)
    iceberg_schemas: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _statement_hash(statement: str) -> str:
    return hashlib.sha1(statement.strip().encode("utf-8")).hexdigest()[:12]


def _coordinator_host_port(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    return host, port


class TrinoClient:
    """Thin Trino REST client for control + verification.

    The client is intentionally limited: it polls ``/v1/statement`` until
    the coordinator returns ``state=FINISHED`` (or an error) and aggregates
    rows so callers can run ``SHOW CATALOGS`` / ``SHOW SCHEMAS`` without
    pulling in a JDBC driver.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        user: str | None = None,
        source: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or trino_coordinator_http_url() or "http://trino:8080").rstrip("/")
        self.user = user or settings.trino_admin_user or "aqp"
        self.source = source or settings.trino_admin_source or "aqp-service-manager"
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    def __enter__(self) -> TrinoClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ------------------------------------------------------------------
    # Coordinator info
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Return the cached coordinator probe payload."""
        return probe_trino_coordinator(timeout_seconds=5.0)

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def query(
        self,
        statement: str,
        *,
        catalog: str | None = None,
        schema: str | None = None,
        max_pages: int = 1000,
    ) -> TrinoQueryResult:
        """Run ``statement`` and aggregate rows. Raises :class:`TrinoClientError` on failure."""
        statement = statement.strip()
        if not statement:
            raise TrinoClientError("statement is empty")
        sh = _statement_hash(statement)
        headers = {
            "X-Trino-User": self.user,
            "X-Trino-Source": self.source,
            "Accept": "application/json",
            "Content-Type": "text/plain",
        }
        if catalog:
            headers["X-Trino-Catalog"] = catalog
        if schema:
            headers["X-Trino-Schema"] = schema
        url = f"{self.base_url}/v1/statement"
        started = time.monotonic()
        with _tracer.start_as_current_span("trino.query") as span:
            span.set_attribute("trino.statement_hash", sh)
            span.set_attribute("trino.statement_preview", statement[:120])
            span.set_attribute("trino.user", self.user)
            try:
                response = self._client.post(url, headers=headers, content=statement)
            except httpx.HTTPError as exc:
                logger.warning("trino query %s failed at submission: %s", sh, exc)
                raise TrinoClientError(f"submit statement failed: {exc}") from exc
            if response.status_code >= 400:
                detail = response.text[:500]
                logger.warning(
                    "trino query %s rejected (%s): %s", sh, response.status_code, detail
                )
                raise TrinoClientError(
                    f"submit statement returned {response.status_code}: {detail}"
                )
            try:
                payload = response.json()
            except ValueError as exc:
                raise TrinoClientError(f"invalid json from /v1/statement: {exc}") from exc

            columns: list[str] = []
            rows: list[list[Any]] = []
            query_id = str(payload.get("id") or "")
            error: dict[str, Any] | None = None
            state = "QUEUED"
            for _ in range(max_pages):
                if columns_payload := payload.get("columns"):
                    columns = [str(c.get("name", "")) for c in columns_payload]
                if data := payload.get("data"):
                    rows.extend(data)
                stats = payload.get("stats") or {}
                state = str(stats.get("state") or state)
                error = payload.get("error") if isinstance(payload.get("error"), dict) else None
                next_uri = payload.get("nextUri")
                if not next_uri or state in {"FINISHED", "FAILED", "CANCELED"} and not next_uri:
                    break
                if not next_uri:
                    break
                try:
                    follow = self._client.get(next_uri, headers=headers)
                except httpx.HTTPError as exc:
                    raise TrinoClientError(f"poll {next_uri} failed: {exc}") from exc
                if follow.status_code == 404:
                    break
                if follow.status_code >= 400:
                    raise TrinoClientError(
                        f"poll {next_uri} returned {follow.status_code}: {follow.text[:300]}"
                    )
                payload = follow.json()
            elapsed = time.monotonic() - started
            span.set_attribute("trino.row_count", len(rows))
            span.set_attribute("trino.elapsed_seconds", elapsed)
            if error:
                logger.warning(
                    "trino query %s failed (state=%s): %s",
                    sh,
                    state,
                    error.get("message"),
                )
                return TrinoQueryResult(
                    query_id=query_id or None,
                    columns=columns,
                    rows=rows,
                    elapsed_seconds=round(elapsed, 4),
                    state=state or "FAILED",
                    error=str(error.get("message") or error),
                    statement=statement,
                    statement_hash=sh,
                )
            logger.info(
                "trino query %s ok (state=%s rows=%d elapsed=%.3fs)",
                sh,
                state or "FINISHED",
                len(rows),
                elapsed,
            )
            return TrinoQueryResult(
                query_id=query_id or None,
                columns=columns,
                rows=rows,
                elapsed_seconds=round(elapsed, 4),
                state=state or "FINISHED",
                statement=statement,
                statement_hash=sh,
            )

    # ------------------------------------------------------------------
    # Catalog/schema verification helpers
    # ------------------------------------------------------------------

    def show_catalogs(self) -> list[str]:
        result = self.query("SHOW CATALOGS")
        return [str(row[0]) for row in result.rows if row]

    def show_schemas(self, catalog: str) -> list[str]:
        result = self.query(f"SHOW SCHEMAS FROM {catalog}")
        return [str(row[0]) for row in result.rows if row]

    def verify(self, *, iceberg_catalog: str | None = None) -> TrinoVerificationResult:
        info = self.info()
        catalog_target = iceberg_catalog or settings.trino_catalog or "iceberg"
        result = TrinoVerificationResult(
            coordinator_ok=bool(info.get("ok")),
            coordinator_url=str(info.get("coordinator_url") or self.base_url),
            node_id=info.get("node_id"),
            node_version=info.get("node_version"),
            query_ok=False,
            iceberg_catalog_ok=False,
            error=info.get("error"),
        )
        if not result.coordinator_ok:
            return result
        try:
            catalogs = self.show_catalogs()
        except TrinoClientError as exc:
            result.error = str(exc)
            return result
        result.query_ok = True
        result.catalogs = catalogs
        if catalog_target in catalogs:
            try:
                schemas = self.show_schemas(catalog_target)
            except TrinoClientError as exc:
                result.error = f"SHOW SCHEMAS FROM {catalog_target}: {exc}"
                return result
            result.iceberg_catalog_ok = True
            result.iceberg_schemas = schemas
        return result

    # ------------------------------------------------------------------
    # Query history (recent failures)
    # ------------------------------------------------------------------

    def query_history(self, *, limit: int = 50) -> list[TrinoQuerySummary]:
        url = f"{self.base_url}/v1/query"
        try:
            response = self._client.get(
                url,
                headers={"Accept": "application/json", "X-Trino-User": self.user},
            )
        except httpx.HTTPError as exc:
            logger.warning("trino query history failed: %s", exc)
            return []
        if response.status_code >= 400:
            logger.warning(
                "trino query history returned %s: %s",
                response.status_code,
                response.text[:300],
            )
            return []
        try:
            payload = response.json()
        except ValueError:
            return []
        if not isinstance(payload, list):
            return []
        summaries: list[TrinoQuerySummary] = []
        for entry in payload[: max(1, int(limit))]:
            if not isinstance(entry, dict):
                continue
            stats = entry.get("queryStats") or {}
            error = entry.get("errorCode") or {}
            summaries.append(
                TrinoQuerySummary(
                    query_id=str(entry.get("queryId") or entry.get("id") or ""),
                    state=str(entry.get("state") or "UNKNOWN"),
                    user=str(entry.get("user") or "") or None,
                    source=str(entry.get("source") or "") or None,
                    catalog=str(entry.get("catalog") or "") or None,
                    schema=str(entry.get("schema") or "") or None,
                    elapsed_seconds=_seconds_or_none(stats.get("elapsedTime")),
                    queued_seconds=_seconds_or_none(stats.get("queuedTime")),
                    error=str(error.get("name")) if error else (str(entry.get("errorType") or "") or None),
                    statement=str(entry.get("query") or entry.get("queryText") or "")[:500],
                    created=str(entry.get("createTime") or entry.get("created") or "") or None,
                )
            )
        return summaries


def _seconds_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0  # Trino returns ms-like numerics in some shapes
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("ms"):
            return float(text[:-2]) / 1000.0
        if text.endswith("s"):
            return float(text[:-1])
        return float(text)
    except ValueError:
        return None


__all__ = [
    "TrinoClient",
    "TrinoClientError",
    "TrinoQueryResult",
    "TrinoQuerySummary",
    "TrinoVerificationResult",
]
