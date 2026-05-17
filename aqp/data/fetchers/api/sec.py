"""SEC EDGAR filings fetcher."""
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
    "source.sec_filings",
    display_name="SEC EDGAR Filings",
    kind=FetcherKind.API,
    description="Fetch SEC EDGAR filings index for a CIK.",
    base_url="https://www.sec.gov",
    auth_type="identity",
    credentials_ref="AQP_SEC_EDGAR_IDENTITY",
    rate_limit=RateLimit(requests_per_second=10),
    capabilities=(FetcherCapability.SUPPORTS_INCREMENTAL.value,),
    domains=("filings.index",),
)
class SecFilingsFetcher(Fetcher):
    """Stream SEC EDGAR filings index rows as Arrow batches."""

    default_rate_limit = RateLimit(requests_per_second=10)

    def __init__(
        self,
        *,
        cik: str,
        forms: list[str] | None = None,
        limit: int = 50,
        chunk_rows: int = 1_000,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        if not cik:
            raise ValueError("SecFilingsFetcher: cik required")
        self.cik = cik
        self.forms = list(forms or [])
        self.limit = max(1, int(limit))
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"sec://{self.cik}"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            from aqp.data.sources.sec.filings import SecFilingsAdapter
        except Exception as exc:  # noqa: BLE001 - optional dep
            logger.warning("SecFilingsFetcher unavailable: %s", exc)
            return

        ctx.emit("source", f"sec cik={self.cik}")
        adapter = SecFilingsAdapter()
        result = adapter.fetch_metadata(
            cik_or_ticker=self.cik,
            form=self.forms or None,
            limit=self.limit,
        )
        rows = list((result or {}).get("filings") or [])
        if not rows:
            return
        try:
            import pandas as pd

            df = pd.DataFrame.from_records(rows)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SecFilingsFetcher failed to normalise rows: %s", exc)
            return
        if df.empty:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
