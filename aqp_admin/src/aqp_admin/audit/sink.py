"""Admin audit sinks — JSONL, HTTP (to monolith), and the no-op logger.

The HTTP sink is the production default for sidecar deployments;
the JSONL sink is the default for local dev and the test suite.
All sinks honour the AGENTS rule 45 redaction contract:
:func:`aqp_platform_core.runtime.workload.redact_payload` strips
any field whose key resembles a credential before persistence.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx

from aqp_platform_core.runtime.workload import redact_payload

from aqp_admin.settings import AdminSettings, get_settings

logger = logging.getLogger("aqp_admin.audit")
_FILE_LOCK = threading.Lock()


@dataclass(slots=True)
class AdminAuditEvent:
    """Single admin audit row.

    Mirrors the shape of :class:`aqp_platform_core.models.workloads.WorkloadRun`
    but with an ``admin.*`` action prefix so postgres consumers can
    filter on it cheaply (``WHERE action LIKE 'admin.%'``).
    """

    run_id: str
    action: str
    target: str
    actor_sub: str
    started_at: datetime
    status: str = "pending"
    org_id: str | None = None
    workspace_id: str | None = None
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "action": self.action,
            "target": self.target,
            "actor_sub": self.actor_sub,
            "status": self.status,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "request_id": self.request_id,
            "payload": self.payload,
            "started_at": _iso(self.started_at),
            "finished_at": _iso(self.finished_at),
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }
        return body


@runtime_checkable
class AdminAuditSink(Protocol):
    """Pluggable persistence for :class:`AdminAuditEvent`.

    Implementations MUST NOT raise — a failed audit write should be
    logged and skipped, not propagate back into the request handler.
    """

    def start(self, event: AdminAuditEvent) -> None: ...

    def finish(self, event: AdminAuditEvent) -> None: ...


class LoggingAdminAuditSink:
    """No-op sink for tests + the slim path. Logs each row."""

    def start(self, event: AdminAuditEvent) -> None:
        logger.info("admin_audit phase=start %s", json.dumps(event.to_dict(), default=str))

    def finish(self, event: AdminAuditEvent) -> None:
        logger.info("admin_audit phase=finish %s", json.dumps(event.to_dict(), default=str))


class JsonlAdminAuditSink:
    """Append-only JSONL sink (local dev + CI)."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def _write(self, body: dict[str, Any]) -> None:
        try:
            with _FILE_LOCK:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(body, default=str))
                    fh.write("\n")
        except OSError as exc:
            logger.warning("jsonl admin_audit write failed (path=%s): %s", self._path, exc)

    def start(self, event: AdminAuditEvent) -> None:
        body = event.to_dict()
        body["phase"] = "start"
        self._write(body)

    def finish(self, event: AdminAuditEvent) -> None:
        body = event.to_dict()
        body["phase"] = "finish"
        self._write(body)


class HttpAdminAuditSink:
    """POST every event to the AQP monolith audit ingest URL.

    The sink uses synchronous httpx so the audit-first contract
    survives without any extra await orchestration in the route
    handler. The :class:`aqp_platform_core.auth.M2MTokenBroker` is
    consulted lazily; missing credentials degrade to a logged
    warning, never a 500.
    """

    def __init__(
        self,
        *,
        url: str,
        bearer_provider: "BearerProvider | None" = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._url = url
        self._timeout = timeout_seconds
        self._bearer_provider = bearer_provider
        self._client = httpx.Client(timeout=timeout_seconds)

    def _bearer(self) -> str | None:
        if self._bearer_provider is None:
            return None
        try:
            return self._bearer_provider()
        except Exception:  # noqa: BLE001
            logger.debug("admin_audit bearer resolve failed", exc_info=True)
            return None

    def _post(self, body: dict[str, Any]) -> None:
        headers = {"Content-Type": "application/json"}
        bearer = self._bearer()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            response = self._client.post(self._url, json=body, headers=headers)
            if response.status_code >= 400:
                logger.warning(
                    "admin_audit POST %s -> HTTP %s body=%s",
                    self._url,
                    response.status_code,
                    response.text[:512],
                )
        except httpx.HTTPError as exc:
            logger.warning("admin_audit POST %s failed: %s", self._url, exc)

    def start(self, event: AdminAuditEvent) -> None:
        body = event.to_dict()
        body["phase"] = "start"
        self._post(body)

    def finish(self, event: AdminAuditEvent) -> None:
        body = event.to_dict()
        body["phase"] = "finish"
        self._post(body)


class BearerProvider(Protocol):
    def __call__(self) -> str | None: ...


_SINK: AdminAuditSink | None = None
_SINK_LOCK = threading.Lock()


def build_default_audit_sink(
    settings: AdminSettings | None = None,
    *,
    bearer_provider: BearerProvider | None = None,
) -> AdminAuditSink:
    """Build the audit sink chosen by ``AQP_ADMIN_AUDIT_SINK``.

    Cached as a process-wide singleton via :func:`get_audit_sink`.
    """
    settings = settings or get_settings()
    kind = (settings.audit_sink or "jsonl").strip().lower()
    if kind == "http":
        if not settings.audit_http_url:
            logger.warning(
                "audit_sink=http but AQP_ADMIN_AUDIT_HTTP_URL is empty; "
                "falling back to LoggingAdminAuditSink"
            )
            return LoggingAdminAuditSink()
        return HttpAdminAuditSink(
            url=settings.audit_http_url,
            bearer_provider=bearer_provider,
        )
    if kind == "log":
        return LoggingAdminAuditSink()
    return JsonlAdminAuditSink(settings.audit_jsonl_path)


def get_audit_sink(
    *,
    bearer_provider: BearerProvider | None = None,
) -> AdminAuditSink:
    global _SINK
    with _SINK_LOCK:
        if _SINK is None:
            _SINK = build_default_audit_sink(bearer_provider=bearer_provider)
    return _SINK


def reset_audit_sink() -> None:
    """Drop the cached sink (test helper)."""
    global _SINK
    with _SINK_LOCK:
        _SINK = None


def new_event(
    *,
    action: str,
    target: str,
    actor_sub: str,
    org_id: str | None = None,
    workspace_id: str | None = None,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> AdminAuditEvent:
    """Build a pre-redacted, pre-stamped :class:`AdminAuditEvent`."""
    return AdminAuditEvent(
        run_id=str(uuid.uuid4()),
        action=action,
        target=target,
        actor_sub=actor_sub,
        org_id=org_id,
        workspace_id=workspace_id,
        request_id=request_id,
        payload=redact_payload(payload or {}),
        started_at=datetime.now(timezone.utc),
    )


def finalise_event(
    event: AdminAuditEvent,
    *,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> AdminAuditEvent:
    """Stamp finish time + result on an in-flight event (no I/O)."""
    finished_at = datetime.now(timezone.utc)
    event.finished_at = finished_at
    event.status = status
    event.duration_ms = (finished_at - event.started_at).total_seconds() * 1000.0
    if result is not None:
        event.result = result
    if error is not None:
        event.error = error
    return event


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


__all__ = [
    "AdminAuditEvent",
    "AdminAuditSink",
    "BearerProvider",
    "HttpAdminAuditSink",
    "JsonlAdminAuditSink",
    "LoggingAdminAuditSink",
    "build_default_audit_sink",
    "finalise_event",
    "get_audit_sink",
    "new_event",
    "reset_audit_sink",
]
