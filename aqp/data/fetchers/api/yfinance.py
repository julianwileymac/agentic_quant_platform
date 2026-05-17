"""Yahoo Finance OHLCV/fundamentals fetcher."""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from aqp.data.engine.nodes import NodeContext
from aqp.data.fabric.schema_registry import FundamentalsSchema, OHLCVSchema
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


@register_source_fetcher(
    "source.yfinance",
    display_name="Yahoo Finance",
    kind=FetcherKind.API,
    description="Fetch OHLCV bars or fundamentals from Yahoo Finance.",
    base_url="https://query1.finance.yahoo.com",
    auth_type=None,
    rate_limit=RateLimit(requests_per_second=2.0),
    capabilities=(
        FetcherCapability.SUPPORTS_INCREMENTAL.value,
        FetcherCapability.SUPPORTS_BACKFILL.value,
    ),
    domains=("equity.bars", "fundamentals.info"),
)
class YFinanceFetcher(Fetcher, FabricFetcherMixin):
    CANONICAL_SCHEMA_CLASS = OHLCVSchema
    SUPPORTED_INTERVALS = ("1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo")
    REQUIRES_AUTH = False
    PROVIDER_NAME = "yFinance"
    MEDALLION_LAYER = "bronze"

    def __init__(
        self,
        *,
        symbols: list[str] | str,
        interval: str = "1d",
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        data_type: Literal["history", "info"] = "history",
        chunk_rows: int = 50_000,
        **kwargs: Any,
    ) -> None:
        parsed_symbols = self._parse_symbols(symbols)
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(
                f"unsupported interval {interval!r}; expected one of {self.SUPPORTED_INTERVALS}"
            )
        if data_type not in {"history", "info"}:
            raise ValueError("data_type must be 'history' or 'info'")
        super().__init__(chunk_rows=chunk_rows, **kwargs)
        self.symbols = parsed_symbols
        self.interval = interval
        self.start = start
        self.end = end
        self.data_type = data_type
        self.chunk_rows = max(1, int(chunk_rows))

    @staticmethod
    def _parse_symbols(symbols: list[str] | str) -> list[str]:
        if isinstance(symbols, str):
            parts = [item.strip() for item in symbols.replace(",", " ").split()]
        else:
            parts = [str(item).strip() for item in symbols]
        parsed = [item for item in parts if item]
        if not parsed:
            raise ValueError("symbols must contain at least one non-empty symbol")
        return parsed

    def source_uri(self) -> str | None:
        return f"yfinance://{','.join(self.symbols)}?interval={self.interval}"

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

        rename_map = {
            "Date": "timestamp",
            "Datetime": "timestamp",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        frame = frame.rename(columns=rename_map)

        if "timestamp" not in frame.columns:
            index_name = str(getattr(frame.index, "name", "") or "")
            if isinstance(frame.index, pd.DatetimeIndex):
                frame = frame.reset_index()
                first = str(frame.columns[0])
                frame = frame.rename(columns={first: "timestamp"})
            elif index_name in {"Date", "Datetime"}:
                frame = frame.reset_index().rename(columns={index_name: "timestamp"})

        feed_id = str(getattr(self, "feed_id", "") or "yfinance")
        if "symbol" not in frame.columns:
            frame["symbol"] = self.symbols[0]
        frame["source_feed_id"] = feed_id
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        try:
            frame["timestamp"] = frame["timestamp"].astype("datetime64[us, UTC]")
        except (TypeError, ValueError):
            pass

        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

        normalized = frame[
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
        table = pa.Table.from_pandas(normalized, preserve_index=False)
        return OHLCVSchema.validate_table(table)

    def _normalize_info(self, rows: list[dict[str, Any]]) -> "pa.Table":
        import pandas as pd
        import pyarrow as pa

        frame = pd.DataFrame(rows)
        frame["source"] = "yfinance"
        frame["report_date"] = pd.to_datetime(
            frame.get("mostRecentQuarter"),
            utc=True,
            errors="coerce",
        )
        try:
            frame["report_date"] = frame["report_date"].astype("datetime64[us, UTC]")
        except (TypeError, ValueError):
            pass
        fiscal_period = frame.get("financialCurrency")
        if fiscal_period is None:
            frame["fiscal_period"] = "unknown"
        else:
            frame["fiscal_period"] = fiscal_period.fillna("unknown").astype(str)
        frame["market_cap"] = pd.to_numeric(frame.get("marketCap"), errors="coerce")
        frame["pe_ratio"] = pd.to_numeric(frame.get("trailingPE"), errors="coerce")
        frame["eps"] = pd.to_numeric(frame.get("trailingEps"), errors="coerce")
        normalized = frame[
            [
                "symbol",
                "source",
                "report_date",
                "fiscal_period",
                "market_cap",
                "pe_ratio",
                "eps",
            ]
        ]
        table = pa.Table.from_pandas(normalized, preserve_index=False)
        return FundamentalsSchema.validate_table(table)

    def fetch(self, ctx: NodeContext) -> Iterator[pa.RecordBatch]:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError("yfinance not installed") from exc

        joined_symbols = " ".join(self.symbols)
        ctx.emit("source", f"yfinance symbols={joined_symbols} data_type={self.data_type}")
        tickers = yf.Tickers(joined_symbols)
        ticker_map = dict(getattr(tickers, "tickers", {}))

        if self.data_type == "history":
            for symbol, ticker in ticker_map.items():
                frame = ticker.history(
                    start=self.start,
                    end=self.end,
                    interval=self.interval,
                    auto_adjust=False,
                )
                if frame is None or frame.empty:
                    continue
                frame = frame.copy()
                frame["symbol"] = symbol
                table = self.normalize_schema(frame)
                yield from table.to_batches(max_chunksize=self.chunk_rows)
            return

        info_rows: list[dict[str, Any]] = []
        for symbol, ticker in ticker_map.items():
            payload = getattr(ticker, "info", None)
            if not isinstance(payload, dict) or not payload:
                continue
            row = dict(payload)
            row["symbol"] = symbol
            info_rows.append(row)
        if not info_rows:
            return
        info_table = self._normalize_info(info_rows)
        yield from info_table.to_batches(max_chunksize=self.chunk_rows)


__all__ = ["YFinanceFetcher"]
