"""AKShare OHLCV specialization with canonical schema output."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from aqp.data.engine.nodes import NodeContext
from aqp.data.fabric.schema_registry import OHLCVSchema
from aqp.data.fetchers.base import (
    Fetcher,
    FetcherCapability,
    FetcherKind,
    RateLimit,
    register_source_fetcher,
)
from aqp.data.fetchers.fabric_mixin import FabricFetcherMixin

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd
    import pyarrow as pa


COLUMN_RENAME = {
    "日期": "timestamp",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "turnover",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "price_change",
    "换手率": "turnover_rate",
}


@register_source_fetcher(
    "source.akshare_ohlcv",
    display_name="AKShare OHLCV",
    kind=FetcherKind.API,
    description="Stream A-share OHLCV bars via AKShare with canonical schema.",
    auth_type=None,
    rate_limit=RateLimit(requests_per_second=3.0),
    capabilities=(FetcherCapability.SUPPORTS_BACKFILL.value,),
    domains=("equity.bars.cn",),
)
class AkshareOHLCVFetcher(Fetcher, FabricFetcherMixin):
    CANONICAL_SCHEMA_CLASS = OHLCVSchema
    SUPPORTED_INTERVALS = ("daily", "weekly", "monthly", "1m", "5m", "15m", "30m", "60m")
    REQUIRES_AUTH = False
    PROVIDER_NAME = "AKShare"
    MEDALLION_LAYER = "bronze"

    def __init__(
        self,
        *,
        symbols: list[str],
        period: str = "daily",
        adjust: str = "",
        start: str | None = None,
        end: str | None = None,
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        cleaned_symbols = [str(symbol).strip() for symbol in symbols if str(symbol).strip()]
        if not cleaned_symbols:
            raise ValueError("symbols must contain at least one non-empty value")
        if period not in self.SUPPORTED_INTERVALS:
            raise ValueError(
                f"unsupported period {period!r}; expected one of {self.SUPPORTED_INTERVALS}"
            )
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.symbols = cleaned_symbols
        self.period = period
        self.adjust = adjust
        self.start = start
        self.end = end
        self.chunk_rows = max(1, int(chunk_rows))

    def source_uri(self) -> str | None:
        return f"akshare://stock_zh_a_hist/{self.period}"

    def normalize_schema(self, records: "pd.DataFrame | pa.Table | list[dict[str, Any]]") -> "pa.Table":
        import pandas as pd
        import pyarrow as pa

        frame: pd.DataFrame
        if isinstance(records, pa.Table):
            frame = records.to_pandas()
        elif isinstance(records, list):
            frame = pd.DataFrame(records)
        elif isinstance(records, pd.DataFrame):
            frame = records.copy()
        elif hasattr(records, "to_pandas") and callable(getattr(records, "to_pandas")):
            frame = records.to_pandas()
        else:
            frame = pd.DataFrame(records)

        frame = frame.rename(columns=COLUMN_RENAME)
        if "timestamp" not in frame.columns:
            frame["timestamp"] = pd.NaT

        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        try:
            frame["timestamp"] = frame["timestamp"].astype("datetime64[us, UTC]")
        except (TypeError, ValueError):
            pass

        if "symbol" not in frame.columns:
            frame["symbol"] = self.symbols[0]
        if "source_feed_id" not in frame.columns:
            frame["source_feed_id"] = str(getattr(self, "feed_id", "") or "akshare")

        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

        canonical = frame[
            [
                "symbol",
                "source_feed_id",
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]
        ]
        table = pa.Table.from_pandas(canonical, preserve_index=False)
        return OHLCVSchema.validate_table(table)

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare not installed") from exc

        import pandas as pd

        ctx.emit("source", f"akshare symbols={len(self.symbols)} period={self.period}")
        source_feed_id = str(getattr(self, "feed_id", "") or "akshare")
        for symbol in self.symbols:
            frame = ak.stock_zh_a_hist(
                symbol=symbol,
                period=self.period,
                start_date=self.start,
                end_date=self.end,
                adjust=self.adjust,
            )
            if frame is None or frame.empty:
                continue
            frame = frame.rename(columns=COLUMN_RENAME)
            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume",
                "turnover",
                "amplitude",
                "pct_change",
                "price_change",
                "turnover_rate",
            ]
            for column in numeric_columns:
                if column in frame.columns:
                    frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
            frame["symbol"] = symbol
            frame["source_feed_id"] = source_feed_id
            normalized = self.normalize_schema(frame)
            yield from self.from_pandas(normalized.to_pandas(), chunk_rows=self.chunk_rows)


__all__ = ["AkshareOHLCVFetcher", "COLUMN_RENAME"]
