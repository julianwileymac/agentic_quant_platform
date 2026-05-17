"""CFPB Consumer Complaints fetcher."""
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
    "source.cfpb",
    display_name="CFPB Consumer Complaint Database",
    kind=FetcherKind.API,
    description="Fetch CFPB consumer complaints by company / product / date range.",
    base_url="https://www.consumerfinance.gov/data-research/consumer-complaints",
    auth_type="none",
    rate_limit=RateLimit(requests_per_minute=60),
    capabilities=(
        FetcherCapability.SUPPORTS_PAGINATION.value,
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
    ),
    domains=("regulatory.cfpb.complaint",),
)
class CfpbComplaintsFetcher(Fetcher):
    """Stream CFPB complaints as Arrow batches."""

    capabilities = (
        FetcherCapability.SUPPORTS_PAGINATION,
        FetcherCapability.SUPPORTS_INCREMENTAL,
    )
    default_rate_limit = RateLimit(requests_per_minute=60)

    def __init__(
        self,
        *,
        company: str | None = None,
        product: str | None = None,
        date_received_min: str | None = None,
        date_received_max: str | None = None,
        max_pages: int = 5,
        page_size: int = 100,
        chunk_rows: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.company = company
        self.product = product
        self.date_received_min = date_received_min
        self.date_received_max = date_received_max
        self.max_pages = max(1, int(max_pages))
        self.page_size = max(1, int(page_size))
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return "cfpb://consumer-complaints"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from aqp.data.sources.cfpb.complaints import CfpbComplaintsAdapter
        except Exception as exc:  # noqa: BLE001
            logger.warning("CfpbComplaintsFetcher unavailable: %s", exc)
            return

        ctx.emit("source", "cfpb consumer complaints")
        adapter = CfpbComplaintsAdapter()
        result = adapter.fetch_observations(
            company=self.company,
            product=self.product,
            date_received_min=self.date_received_min,
            date_received_max=self.date_received_max,
            max_pages=self.max_pages,
            page_size=self.page_size,
            persist=False,
            emit_lineage=False,
        )
        df = getattr(result, "data", None)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
