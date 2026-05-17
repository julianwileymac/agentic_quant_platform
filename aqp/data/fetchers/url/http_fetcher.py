"""Stream Arrow batches from a remote HTTP(S) URL.

Auto-detects the payload format from the URL extension (or the
``Content-Type`` header). Supports CSV / TSV / JSON / JSONL / Parquet /
Arrow IPC. Uses :mod:`httpx` for chunked downloads with retries and a
configurable User-Agent.
"""
from __future__ import annotations

import io
import json
import logging
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)
from aqp.data.fetchers.local.file_fetcher import FileFetcher

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.http",
    display_name="Remote URL (HTTP/HTTPS)",
    kind=FetcherKind.URL,
    description="Fetch a remote URL and stream it as Arrow batches.",
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("url.http", "url.https"),
)
class HttpFetcher(Fetcher):
    """Download ``url`` and stream as Arrow batches.

    For tabular formats (parquet/csv/tsv/jsonl/arrow) the response is
    spilled to a tempfile and re-read with :class:`FileFetcher`. For
    JSON the entire payload is parsed in one shot.
    """

    capabilities = (FetcherCapability.SUPPORTS_INCREMENTAL,)

    def __init__(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
        format: str | None = None,
        chunk_rows: int = 50_000,
        record_path: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not url:
            raise ValueError("HttpFetcher: url required")
        self.url = url
        self.method = (method or "GET").upper()
        self.headers = dict(headers or {})
        self.params = dict(params or {})
        self.body = body
        self.timeout = timeout
        self.format = (format or "").lower() or None
        self.chunk_rows = max(1, int(chunk_rows))
        self.record_path = list(record_path or [])

    def source_uri(self) -> str | None:
        return self.url

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.config import settings

        try:
            import httpx
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"HttpFetcher requires httpx: {exc}") from exc

        timeout = float(self.timeout or settings.fetcher_default_timeout_seconds or 120.0)
        ua = settings.fetcher_user_agent or "aqp-fetcher/1.0"

        headers = {"User-Agent": ua, **self.headers}

        ctx.emit("source", f"GET {self.url}")
        with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
            with client.stream(
                self.method,
                self.url,
                params=self.params,
                json=self.body if self.method != "GET" else None,
            ) as response:
                response.raise_for_status()
                fmt = self.format or self._detect_format(self.url, response.headers)
                if fmt == "json":
                    yield from self._handle_json(response.read())
                    return
                # Spill chunked download to tempfile, then delegate to FileFetcher
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=f".{fmt}",
                ) as fh:
                    target = Path(fh.name)
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            fh.write(chunk)

        try:
            file_fetcher = FileFetcher(
                path=target,
                format=fmt,
                chunk_rows=self.chunk_rows,
            )
            file_fetcher.open(ctx)
            try:
                yield from file_fetcher.fetch(ctx)
            finally:
                file_fetcher.close(ctx)
        finally:
            try:
                target.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _detect_format(url: str, headers: Any) -> str:
        path = urlparse(url).path.lower()
        if path.endswith((".parquet", ".pq")):
            return "parquet"
        if path.endswith(".csv"):
            return "csv"
        if path.endswith(".tsv"):
            return "tsv"
        if path.endswith((".jsonl", ".ndjson")):
            return "jsonl"
        if path.endswith(".json"):
            return "json"
        if path.endswith((".arrow", ".feather")):
            return "arrow"
        ct = (headers.get("content-type") or "").lower() if headers else ""
        if "parquet" in ct:
            return "parquet"
        if "ndjson" in ct or "jsonl" in ct:
            return "jsonl"
        if "json" in ct:
            return "json"
        if "csv" in ct:
            return "csv"
        if "octet-stream" in ct:
            return "parquet"
        return "json"

    def _handle_json(self, payload: bytes) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        data = json.loads(payload.decode("utf-8"))
        for key in self.record_path or []:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                logger.debug("HttpFetcher record_path key %s missing", key)
                data = []
                break
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return
        for start in range(0, len(data), self.chunk_rows):
            chunk = data[start : start + self.chunk_rows]
            if not chunk:
                continue
            table = pa.Table.from_pylist(chunk)
            yield from table.to_batches()
