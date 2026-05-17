"""FinanceDatabase fetcher (symbol taxonomy seed).

Reads the bz2-compressed CSVs the FinanceDatabase project ships at
``compression/<asset_class>.bz2`` (mirroring the local layout + the
GitHub raw URL). Useful for seeding the entity registry with a wide
symbol catalog (Equities, ETFs, Funds, Indices, Currencies, Cryptos,
Money Markets) without paying the price of a full ingest of every
data vendor.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
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


_VALID_ASSETS = (
    "equities",
    "etfs",
    "funds",
    "indices",
    "currencies",
    "cryptos",
    "moneymarkets",
)


@register_source_fetcher(
    "source.finance_database",
    display_name="FinanceDatabase (symbol taxonomy)",
    kind=FetcherKind.URL,
    description="Load a FinanceDatabase asset class (equities/etfs/funds/...) as Arrow.",
    base_url="https://github.com/JerBouma/FinanceDatabase",
    auth_type="none",
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.SUPPORTS_BACKFILL.value,
    ),
    domains=(
        "taxonomy.equity",
        "taxonomy.etf",
        "taxonomy.fund",
        "taxonomy.index",
        "taxonomy.currency",
        "taxonomy.crypto",
        "taxonomy.money_market",
    ),
)
class FinanceDatabaseFetcher(Fetcher):
    """Stream a FinanceDatabase compressed CSV as Arrow batches.

    ``asset_class`` selects the asset family. ``base_url`` defaults to
    the official GitHub raw mirror and is overridable for offline
    bundles via :class:`aqp.config.Settings.finance_database_repo`.
    """

    def __init__(
        self,
        *,
        asset_class: str,
        base_url: str | None = None,
        chunk_rows: int = 25_000,
        country: str | None = None,
        sector: str | None = None,
        industry: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        asset_class = (asset_class or "").lower().strip()
        if asset_class not in _VALID_ASSETS:
            raise ValueError(
                f"FinanceDatabaseFetcher: asset_class must be one of {_VALID_ASSETS!r}"
            )
        self.asset_class = asset_class
        self.base_url = base_url
        self.chunk_rows = max(1, int(chunk_rows))
        self.country = country
        self.sector = sector
        self.industry = industry

    def source_uri(self) -> str | None:
        from aqp.config import settings

        base = self.base_url or settings.finance_database_repo
        return f"{base.rstrip('/')}/{self.asset_class}.bz2"

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            logger.warning("FinanceDatabaseFetcher requires pandas: %s", exc)
            return

        url = self.source_uri()
        ctx.emit("source", f"finance_database asset={self.asset_class}")
        df = pd.read_csv(url, compression="bz2", index_col=0, low_memory=False)
        if "symbol" not in df.columns:
            df = df.reset_index().rename(columns={df.index.name or "index": "symbol"})
        if self.country and "country" in df.columns:
            df = df[df["country"].str.lower() == self.country.lower()]
        if self.sector and "sector" in df.columns:
            df = df[df["sector"].str.lower() == self.sector.lower()]
        if self.industry and "industry" in df.columns:
            df = df[df["industry"].str.lower() == self.industry.lower()]
        df = df.reset_index(drop=True)
        if len(df) == 0:
            return
        yield from self.from_pandas(df, chunk_rows=self.chunk_rows)
