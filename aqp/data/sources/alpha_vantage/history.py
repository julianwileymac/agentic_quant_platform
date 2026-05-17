"""Alpha Vantage stock history ingestion into Iceberg."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data.sources.alpha_vantage.catalog import (
    AlphaVantageFunction,
    get_function,
    iceberg_namespace,
)
from aqp.data.sources.alpha_vantage.client import AlphaVantageClient
from aqp.data.sources.alpha_vantage.coordination import (
    AlphaVantageHistoryCoordinationRequest,
    AlphaVantageRequestCoordinator,
    ProgressCallback,
)
from aqp.data.sources.alpha_vantage.endpoints._base import coerce_stock_intraday_interval

logger = logging.getLogger(__name__)


_FUNCTION_TO_ID: dict[str, str] = {
    "intraday": "timeseries.intraday",
    "daily": "timeseries.daily",
    "daily_adjusted": "timeseries.daily_adjusted",
    "weekly": "timeseries.weekly_adjusted",
    "weekly_adjusted": "timeseries.weekly_adjusted",
    "monthly": "timeseries.monthly_adjusted",
    "monthly_adjusted": "timeseries.monthly_adjusted",
}


def _resolve_function_metadata(function: str) -> AlphaVantageFunction | None:
    key = (function or "").strip().lower()
    function_id = _FUNCTION_TO_ID.get(key, key)
    return get_function(function_id)


@dataclass
class AlphaVantageHistoryRequest:
    symbols: list[str]
    start: str | None = None
    end: str | None = None
    function: str = "daily_adjusted"
    interval: str | None = None
    outputsize: str = "full"
    month: str | None = None
    adjusted: bool | None = None
    extended_hours: bool | None = None
    entitlement: str | None = None
    namespace: str = ""
    table: str = ""
    cache: bool = True
    cache_ttl: float | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)

    @property
    def iceberg_identifier(self) -> str:
        ns = self.namespace or iceberg_namespace()
        if self.table:
            return f"{ns}.{self.table}"
        meta = _resolve_function_metadata(self.function)
        if meta and meta.iceberg_table:
            return f"{ns}.{meta.iceberg_table}"
        return f"{ns}.stock_history"


@dataclass
class AlphaVantageHistoryResult:
    iceberg_identifier: str
    rows_written: int
    symbols: list[str]
    start: str | None
    end: str | None
    function: str
    interval: str | None
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iceberg_identifier": self.iceberg_identifier,
            "rows_written": int(self.rows_written),
            "symbols": list(self.symbols),
            "start": self.start,
            "end": self.end,
            "function": self.function,
            "interval": self.interval,
            "lineage": dict(self.lineage),
        }


class AlphaVantageHistoryPipeline:
    """Fetch Alpha Vantage time series and persist canonical bars to Iceberg."""

    def __init__(
        self,
        client: AlphaVantageClient | None = None,
        *,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self.client = client or AlphaVantageClient()
        self._owns_client = client is None
        self.progress_cb = progress_cb

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def run(self, req: AlphaVantageHistoryRequest) -> AlphaVantageHistoryResult:
        coordinator = AlphaVantageRequestCoordinator(self.client, progress_cb=self.progress_cb)
        result = coordinator.run_history(
            AlphaVantageHistoryCoordinationRequest(
                symbols=_clean_symbols(req.symbols),
                iceberg_identifier=req.iceberg_identifier,
                table=req.table,
                start=req.start,
                end=req.end,
                function=req.function,
                interval=req.interval,
                outputsize=req.outputsize,
                month=req.month,
                adjusted=req.adjusted,
                extended_hours=req.extended_hours,
                entitlement=req.entitlement,
                cache=req.cache,
                cache_ttl=req.cache_ttl,
                extra_params=dict(req.extra_params or {}),
            )
        )
        return AlphaVantageHistoryResult(
            iceberg_identifier=req.iceberg_identifier,
            rows_written=result.rows_written,
            symbols=result.symbols or _clean_symbols(req.symbols),
            start=result.start or req.start,
            end=result.end or req.end,
            function=req.function,
            interval=req.interval,
            lineage=result.lineage,
        )

    def fetch(self, req: AlphaVantageHistoryRequest) -> pd.DataFrame:
        rows: list[pd.DataFrame] = []
        for raw_symbol in _clean_symbols(req.symbols):
            sym = _to_symbol(raw_symbol)
            payload = self._fetch_symbol(req, sym.ticker)
            bars = list(getattr(payload, "bars", []) or [])
            if not bars:
                continue
            frame = _normalize_bars(bars, sym.vt_symbol)
            frame = _filter_range(frame, req.start, req.end)
            if not frame.empty:
                frame["source"] = "alpha_vantage"
                frame["function"] = req.function
                rows.append(frame)
        if not rows:
            return pd.DataFrame()
        out = pd.concat(rows, ignore_index=True)
        return out.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)

    def _fetch_symbol(self, req: AlphaVantageHistoryRequest, ticker: str) -> Any:
        options = {
            "_cache": req.cache,
            "_cache_ttl": req.cache_ttl,
            **dict(req.extra_params or {}),
        }
        function = req.function.strip().lower()
        if function == "intraday":
            return self.client.timeseries.intraday(
                ticker,
                interval=coerce_stock_intraday_interval(req.interval),
                outputsize=req.outputsize,
                month=req.month,
                adjusted=req.adjusted,
                extended_hours=req.extended_hours,
                entitlement=req.entitlement,
                **options,
            )
        if function == "daily":
            return self.client.timeseries.daily(ticker, outputsize=req.outputsize, **options)
        if function == "weekly":
            return self.client.timeseries.weekly(ticker, **options)
        if function == "weekly_adjusted":
            return self.client.timeseries.weekly_adjusted(ticker, **options)
        if function == "monthly":
            return self.client.timeseries.monthly(ticker, **options)
        if function == "monthly_adjusted":
            return self.client.timeseries.monthly_adjusted(ticker, **options)
        return self.client.timeseries.daily_adjusted(ticker, outputsize=req.outputsize, **options)


def ingest_history(**kwargs: Any) -> AlphaVantageHistoryResult:
    progress_cb = kwargs.pop("progress_cb", None)
    req = AlphaVantageHistoryRequest(**kwargs)
    pipeline = AlphaVantageHistoryPipeline(progress_cb=progress_cb)
    try:
        return pipeline.run(req)
    finally:
        pipeline.close()


def _clean_symbols(symbols: Iterable[str]) -> list[str]:
    return [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]


def _to_symbol(raw: str) -> Symbol:
    if "." in raw:
        return Symbol.parse(raw)
    return Symbol.parse(f"{raw}.{getattr(settings, 'default_exchange', 'NASDAQ')}")


def _normalize_bars(bars: list[dict[str, Any]], vt_symbol: str) -> pd.DataFrame:
    frame = pd.DataFrame(bars)
    if frame.empty:
        return frame
    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    if "timestamp" not in frame.columns:
        raise ValueError("Alpha Vantage bar payload missing timestamp")
    for column in ("open", "high", "low", "close", "adjusted_close", "volume", "dividend_amount", "split_coefficient"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    keep = [
        "timestamp",
        "vt_symbol",
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ]
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["timestamp"] = frame["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[us]")
    frame["vt_symbol"] = vt_symbol
    for column in keep:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[keep].dropna(subset=["timestamp", "open", "high", "low", "close"])
    return frame


def _filter_range(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if frame.empty:
        return frame
    out = frame
    if start:
        out = out[out["timestamp"] >= _naive_utc_timestamp(start)]
    if end:
        out = out[out["timestamp"] <= _naive_utc_timestamp(end)]
    return out


def _naive_utc_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts
    return ts.tz_convert("UTC").tz_localize(None)


__all__ = [
    "AlphaVantageHistoryPipeline",
    "AlphaVantageHistoryRequest",
    "AlphaVantageHistoryResult",
    "ingest_history",
]
