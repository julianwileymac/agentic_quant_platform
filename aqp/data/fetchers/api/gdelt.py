"""GDELT GKG events fetcher."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    register_source_fetcher,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa


@register_source_fetcher(
    "source.gdelt",
    display_name="GDELT GKG 2.0",
    kind=FetcherKind.URL,
    description="Fetch a GDELT GKG window and stream as Arrow batches.",
    base_url="http://data.gdeltproject.org/gkg",
    auth_type="none",
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.SUPPORTS_BACKFILL.value,
    ),
    domains=("events.gdelt", "news"),
)
class GdeltFetcher(Fetcher):
    """Stream a GDELT GKG window as Arrow batches.

    ``start`` / ``end`` define the window (defaults to the last 24 h).
    ``subject_filter_only`` reuses the configured filter to drop
    irrelevant rows.
    """

    capabilities = (
        FetcherCapability.SUPPORTS_INCREMENTAL,
        FetcherCapability.SUPPORTS_BACKFILL,
    )

    def __init__(
        self,
        *,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        subject_filter_only: bool | None = None,
        max_files: int | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.start = start
        self.end = end
        self.subject_filter_only = subject_filter_only
        self.max_files = max_files
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return "gdelt://gkg"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from aqp.data.sources.gdelt.adapter import GDeltAdapter
        except Exception as exc:  # noqa: BLE001
            logger.warning("GdeltFetcher unavailable: %s", exc)
            return

        end = self.end or datetime.utcnow()
        start = self.start or (
            (end if isinstance(end, datetime) else datetime.utcnow())
            - timedelta(days=1)
        )
        ctx.emit("source", f"gdelt start={start} end={end}")
        adapter = GDeltAdapter()
        result = adapter.fetch_observations(
            start=start,
            end=end,
            subject_filter_only=self.subject_filter_only,
            max_files=self.max_files,
            persist=False,
            emit_lineage=False,
        )
        df = getattr(result, "data", None)
        if df is None or len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
