"""USPTO patents / trademarks / assignments fetcher."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    RateLimit,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.uspto",
    display_name="USPTO PatentsView / PEDS / TSDR",
    kind=FetcherKind.API,
    description="Fetch USPTO patents / trademarks / assignments.",
    base_url="https://search.patentsview.org/api/v1",
    auth_type="api_key",
    credentials_ref="AQP_USPTO_API_KEY",
    rate_limit=RateLimit(requests_per_minute=45),
    capabilities=(
        FetcherCapability.SUPPORTS_PAGINATION.value,
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
    ),
    domains=(
        "regulatory.uspto.patent",
        "regulatory.uspto.trademark",
        "regulatory.uspto.assignment",
    ),
)
class UsptoFetcher(Fetcher):
    """Stream USPTO records as Arrow batches."""

    capabilities = (
        FetcherCapability.SUPPORTS_PAGINATION,
        FetcherCapability.SUPPORTS_INCREMENTAL,
    )
    default_rate_limit = RateLimit(requests_per_minute=45)

    def __init__(
        self,
        *,
        endpoint: str = "patents",
        query: dict[str, Any] | None = None,
        max_pages: int = 5,
        per_page: int = 100,
        chunk_rows: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        endpoint = (endpoint or "patents").lower()
        if endpoint not in {"patents", "trademarks", "assignments"}:
            raise ValueError(f"UsptoFetcher: unsupported endpoint {endpoint!r}")
        self.endpoint = endpoint
        self.query = dict(query or {})
        self.max_pages = max(1, int(max_pages))
        self.per_page = max(1, int(per_page))
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"uspto://{self.endpoint}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            if self.endpoint == "patents":
                from aqp.data.sources.uspto.patents import UsptoPatentsAdapter

                adapter = UsptoPatentsAdapter()
            elif self.endpoint == "trademarks":
                from aqp.data.sources.uspto.trademarks import UsptoTrademarksAdapter

                adapter = UsptoTrademarksAdapter()
            else:
                from aqp.data.sources.uspto.assignments import UsptoAssignmentsAdapter

                adapter = UsptoAssignmentsAdapter()
        except Exception as exc:  # noqa: BLE001
            logger.warning("UsptoFetcher unavailable: %s", exc)
            return

        ctx.emit("source", f"uspto endpoint={self.endpoint}")
        result = adapter.fetch_observations(
            query=self.query,
            per_page=self.per_page,
            max_pages=self.max_pages,
            persist=False,
            emit_lineage=False,
        )
        df = getattr(result, "data", None)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
