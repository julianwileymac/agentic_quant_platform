"""Generic REST API fetcher.

Lightweight HTTP-JSON fetcher that supports auth via header/key, simple
pagination, and JSON record extraction. The dedicated AV / FRED / SEC
adapters subclass this when they need more bespoke behaviour.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    Pagination,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.rest_api",
    display_name="Generic REST API",
    kind=FetcherKind.API,
    description="Generic REST API fetcher (JSON, pagination, header auth).",
    capabilities=(
        FetcherCapability.SUPPORTS_PAGINATION.value,
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
    ),
    domains=("api.rest",),
)
class RestApiFetcher(Fetcher):
    """Hit a paginated REST endpoint and stream the records as Arrow.

    Pagination knobs (one of the three flavors):

    - Page-number: ``pagination={page_param: "page", page_size_param:
      "page_size", page_size: 100, max_pages: 10}``.
    - Cursor: ``pagination={cursor_param: "cursor", cursor_field:
      "next_cursor", max_pages: 10}``.
    - Next link: ``pagination={next_link_field: "next"}``.
    """

    capabilities = (
        FetcherCapability.SUPPORTS_PAGINATION,
        FetcherCapability.SUPPORTS_INCREMENTAL,
    )

    def __init__(
        self,
        *,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        record_path: list[str] | None = None,
        pagination: dict[str, Any] | Pagination | None = None,
        chunk_rows: int = 50_000,
        timeout: float | None = None,
        api_key_param: str | None = None,
        api_key_value: str | None = None,
        api_key_header: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not url:
            raise ValueError("RestApiFetcher: url required")
        self.url = url
        self.method = (method or "GET").upper()
        self.headers = dict(headers or {})
        self.params = dict(params or {})
        self.body = body
        self.record_path = list(record_path or [])
        self.pagination_spec = (
            pagination
            if isinstance(pagination, Pagination)
            else (Pagination(**pagination) if pagination else None)
        )
        self.chunk_rows = max(1, int(chunk_rows))
        self.timeout = timeout
        self.api_key_param = api_key_param
        self.api_key_value = api_key_value
        self.api_key_header = api_key_header

    def source_uri(self) -> str | None:
        return self.url

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        from aqp.config import settings

        try:
            import httpx
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"RestApiFetcher requires httpx: {exc}") from exc

        timeout = float(self.timeout or settings.fetcher_default_timeout_seconds or 120.0)
        headers = {"User-Agent": settings.fetcher_user_agent or "aqp-fetcher/1.0", **self.headers}
        if self.api_key_header and self.api_key_value:
            headers[self.api_key_header] = self.api_key_value

        params = dict(self.params)
        if self.api_key_param and self.api_key_value:
            params[self.api_key_param] = self.api_key_value

        client = httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)
        try:
            yield from self._iter_pages(ctx, client, params)
        finally:
            client.close()

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    def _iter_pages(
        self,
        ctx: NodeContext,
        client: Any,
        base_params: dict[str, Any],
    ) -> Iterator[pa.RecordBatch]:
        spec = self.pagination_spec
        url = self.url
        params = dict(base_params)

        if spec and spec.cursor_param:
            yield from self._cursor_pagination(ctx, client, url, params, spec)
            return
        if spec and spec.next_link_field:
            yield from self._next_link_pagination(ctx, client, url, params, spec)
            return
        if spec and spec.page_param:
            yield from self._page_pagination(ctx, client, url, params, spec)
            return
        # Single shot
        yield from self._records_to_batches(self._fetch_records(ctx, client, url, params))

    def _fetch_records(
        self,
        ctx: NodeContext,
        client: Any,
        url: str,
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        ctx.emit("source", f"{self.method} {url}")
        if self.method == "GET":
            response = client.get(url, params=params)
        else:
            response = client.request(self.method, url, params=params, json=self.body)
        response.raise_for_status()
        payload = response.json()
        records = self._extract_records(payload)
        return records, payload

    def _extract_records(self, payload: Any) -> list[dict[str, Any]]:
        data = payload
        for key in self.record_path or []:
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                return []
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        return []

    def _cursor_pagination(
        self,
        ctx: NodeContext,
        client: Any,
        url: str,
        params: dict[str, Any],
        spec: Pagination,
    ) -> Iterator[pa.RecordBatch]:
        cursor = None
        page = 0
        while True:
            page += 1
            if cursor is not None and spec.cursor_param:
                params = {**params, spec.cursor_param: cursor}
            records, payload = self._fetch_records(ctx, client, url, params)
            if not records:
                break
            yield from self._records_to_batches(records)
            if spec.max_pages and page >= int(spec.max_pages):
                break
            cursor = payload.get(spec.cursor_field) if isinstance(payload, dict) else None
            if not cursor:
                break

    def _next_link_pagination(
        self,
        ctx: NodeContext,
        client: Any,
        url: str,
        params: dict[str, Any],
        spec: Pagination,
    ) -> Iterator[pa.RecordBatch]:
        page = 0
        next_link = url
        while next_link:
            page += 1
            records, payload = self._fetch_records(ctx, client, next_link, params)
            params = {}  # next link encodes the params
            if not records:
                break
            yield from self._records_to_batches(records)
            if spec.max_pages and page >= int(spec.max_pages):
                break
            next_link = payload.get(spec.next_link_field) if isinstance(payload, dict) else None

    def _page_pagination(
        self,
        ctx: NodeContext,
        client: Any,
        url: str,
        params: dict[str, Any],
        spec: Pagination,
    ) -> Iterator[pa.RecordBatch]:
        page = int(spec.start_page or 1)
        seen = 0
        while True:
            page_params = dict(params)
            if spec.page_param:
                page_params[spec.page_param] = page
            if spec.page_size_param and spec.page_size:
                page_params[spec.page_size_param] = int(spec.page_size)
            records, _payload = self._fetch_records(ctx, client, url, page_params)
            if not records:
                break
            yield from self._records_to_batches(records)
            seen += len(records)
            if spec.max_pages and page - int(spec.start_page or 1) + 1 >= int(spec.max_pages):
                break
            page += 1

    # ------------------------------------------------------------------
    # Arrow conversion
    # ------------------------------------------------------------------

    def _records_to_batches(self, records: list[dict[str, Any]]) -> Iterator[pa.RecordBatch]:
        import pyarrow as pa

        if not records:
            return
        for start in range(0, len(records), self.chunk_rows):
            chunk = records[start : start + self.chunk_rows]
            if not chunk:
                continue
            table = pa.Table.from_pylist(chunk)
            yield from table.to_batches()
