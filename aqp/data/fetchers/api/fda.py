"""FDA openFDA fetcher (applications, recalls, adverse events)."""
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
    "source.fda",
    display_name="FDA openFDA",
    kind=FetcherKind.API,
    description="Fetch FDA drug applications / adverse events / recalls.",
    base_url="https://api.fda.gov",
    auth_type="api_key",
    credentials_ref="AQP_FDA_API_KEY",
    rate_limit=RateLimit(requests_per_minute=240),
    capabilities=(
        FetcherCapability.SUPPORTS_PAGINATION.value,
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
    ),
    domains=(
        "regulatory.fda.application",
        "regulatory.fda.adverse_event",
        "regulatory.fda.recall",
    ),
)
class FdaFetcher(Fetcher):
    """Stream FDA records as Arrow batches.

    ``endpoint`` selects the openFDA endpoint:

    - ``applications`` — drug application records.
    - ``recalls`` — enforcement recall reports.
    - ``adverse_events`` — adverse event reports.
    """

    capabilities = (
        FetcherCapability.SUPPORTS_PAGINATION,
        FetcherCapability.SUPPORTS_INCREMENTAL,
    )
    default_rate_limit = RateLimit(requests_per_minute=240)

    def __init__(
        self,
        *,
        endpoint: str = "applications",
        search: str | None = None,
        limit: int = 100,
        skip: int = 0,
        max_pages: int = 5,
        chunk_rows: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        endpoint = (endpoint or "applications").lower()
        if endpoint not in {"applications", "recalls", "adverse_events"}:
            raise ValueError(
                f"FdaFetcher: unsupported endpoint {endpoint!r}"
            )
        self.endpoint = endpoint
        self.search = search
        self.limit = max(1, int(limit))
        self.skip = max(0, int(skip))
        self.max_pages = max(1, int(max_pages))
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"fda://{self.endpoint}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            if self.endpoint == "applications":
                from aqp.data.sources.fda.applications import FdaApplicationsAdapter

                adapter = FdaApplicationsAdapter()
            elif self.endpoint == "recalls":
                from aqp.data.sources.fda.recalls import FdaRecallsAdapter

                adapter = FdaRecallsAdapter()
            else:
                from aqp.data.sources.fda.adverse_events import FdaAdverseEventsAdapter

                adapter = FdaAdverseEventsAdapter()
        except Exception as exc:  # noqa: BLE001
            logger.warning("FdaFetcher unavailable: %s", exc)
            return

        ctx.emit("source", f"fda endpoint={self.endpoint}")
        result = adapter.fetch_observations(
            search=self.search,
            limit=self.limit,
            skip=self.skip,
            max_pages=self.max_pages,
            persist=False,
            emit_lineage=False,
        )
        df = getattr(result, "data", None)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
