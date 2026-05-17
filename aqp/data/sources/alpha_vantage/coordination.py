"""Coordinated Alpha Vantage request, append, and catalog registration flows."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from aqp.config import settings
from aqp.core.types import Symbol
from aqp.data import iceberg_catalog
from aqp.data.catalog import register_dataset_version
from aqp.data.sources.alpha_vantage._errors import AlphaVantagePayloadError
from aqp.data.sources.alpha_vantage.catalog import AlphaVantageFunction, get_function
from aqp.data.sources.alpha_vantage.endpoints._base import coerce_stock_intraday_interval
from aqp.observability import get_tracer

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]

_FUNCTION_TO_ID: dict[str, str] = {
    "intraday": "timeseries.intraday",
    "daily": "timeseries.daily",
    "daily_adjusted": "timeseries.daily_adjusted",
    "weekly": "timeseries.weekly_adjusted",
    "weekly_adjusted": "timeseries.weekly_adjusted",
    "monthly": "timeseries.monthly_adjusted",
    "monthly_adjusted": "timeseries.monthly_adjusted",
}


@dataclass(frozen=True)
class AlphaVantageHistoryCoordinationRequest:
    symbols: list[str]
    iceberg_identifier: str
    table: str = ""
    start: str | None = None
    end: str | None = None
    function: str = "daily_adjusted"
    interval: str | None = None
    outputsize: str = "full"
    month: str | None = None
    adjusted: bool | None = None
    extended_hours: bool | None = None
    entitlement: str | None = None
    cache: bool = True
    cache_ttl: float | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AlphaVantageIntradayCoordinationRequest:
    component_id: str
    vt_symbol: str
    ticker: str
    month: str
    interval: str
    iceberg_identifier: str
    function: str = "TIME_SERIES_INTRADAY"
    function_id: str = "timeseries.intraday"
    outputsize: str = "full"
    adjusted: bool = True
    extended_hours: bool = True
    entitlement: str | None = None
    source: dict[str, Any] = field(default_factory=dict)
    cache: bool = True
    cache_ttl: float | None = None

    @classmethod
    def from_component(
        cls,
        component: Any,
        *,
        iceberg_identifier: str,
        cache: bool = True,
        cache_ttl: float | None = None,
    ) -> "AlphaVantageIntradayCoordinationRequest":
        return cls(
            component_id=str(component.component_id),
            vt_symbol=str(component.vt_symbol),
            ticker=str(component.ticker),
            month=str(component.month),
            interval=str(component.interval),
            iceberg_identifier=iceberg_identifier,
            function=str(component.function),
            function_id=str(component.function_id),
            outputsize=str(component.outputsize),
            adjusted=bool(component.adjusted),
            extended_hours=bool(component.extended_hours),
            entitlement=component.entitlement,
            source=dict(component.source or {}),
            cache=cache,
            cache_ttl=cache_ttl,
        )


@dataclass
class AlphaVantageCoordinationResult:
    status: str
    iceberg_identifier: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    fetched_rows: int = 0
    duplicate_rows: int = 0
    rows_written: int = 0
    symbols: list[str] = field(default_factory=list)
    start: str | None = None
    end: str | None = None
    function: str = ""
    interval: str | None = None
    lineage: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def debug_extras(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "iceberg_identifier": self.iceberg_identifier,
            "fetched_rows": int(self.fetched_rows),
            "duplicate_rows": int(self.duplicate_rows),
            "rows_written": int(self.rows_written),
            "symbol_count": len(self.symbols),
            "error": self.error,
        }


class AlphaVantageRequestCoordinator:
    """Coordinate Alpha Vantage fetch, normalization, append, and registration."""

    def __init__(self, client: Any, *, progress_cb: ProgressCallback | None = None) -> None:
        self.client = client
        self.progress_cb = progress_cb
        self._tracer = get_tracer("aqp.data.alpha_vantage.coordination")

    def run_history(
        self,
        req: AlphaVantageHistoryCoordinationRequest,
    ) -> AlphaVantageCoordinationResult:
        meta = _resolve_function_metadata(req.function)
        domain = (meta.domain if meta else None) or "market.bars"
        partition_spec = _partition_spec(meta)
        request_id = _request_id("history", req.function, req.interval, len(req.symbols))
        base = {
            "request_id": request_id,
            "function": req.function,
            "function_id": meta.id if meta else _FUNCTION_TO_ID.get(req.function, req.function),
            "interval": req.interval,
            "month": req.month,
            "iceberg_identifier": req.iceberg_identifier,
            "symbol_count": len(req.symbols),
        }
        with self._tracer.start_as_current_span("alpha_vantage.coordinate") as span:
            _set_span_attributes(span, base)
            self._emit("debug", "Alpha Vantage history coordination started", base)
            frames: list[pd.DataFrame] = []
            errors: list[dict[str, Any]] = []
            for raw_symbol in _clean_symbols(req.symbols):
                sym = _to_symbol(raw_symbol)
                symbol_base = {**base, "ticker": sym.ticker, "vt_symbol": sym.vt_symbol}
                frame, error = self._fetch_history_symbol(req, sym, symbol_base)
                if error:
                    errors.append(error)
                    continue
                if frame is not None and not frame.empty:
                    frames.append(frame)

            if not frames:
                result = AlphaVantageCoordinationResult(
                    status="skipped",
                    iceberg_identifier=req.iceberg_identifier,
                    fetched_rows=0,
                    rows_written=0,
                    symbols=_clean_symbols(req.symbols),
                    start=req.start,
                    end=req.end,
                    function=req.function,
                    interval=req.interval,
                    lineage={"errors": errors} if errors else {},
                    errors=errors,
                    error="no_provider_rows" if not errors else "no_successful_requests",
                )
                self._emit("debug", "Alpha Vantage history coordination produced no rows", {**base, **result.debug_extras()})
                return result

            frame = pd.concat(frames, ignore_index=True).sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
            fetched_rows = int(len(frame))
            try:
                lineage = self._append_history(
                    req=req,
                    frame=frame,
                    domain=domain,
                    meta=meta,
                    partition_spec=partition_spec,
                    base=base,
                )
            except Exception as exc:
                span.record_exception(exc)
                self._emit("error", "Alpha Vantage history append failed", {**base, "error": str(exc), "fetched_rows": fetched_rows})
                raise

            if errors:
                lineage = {**lineage, "errors": errors}
            result = AlphaVantageCoordinationResult(
                status="partial" if errors else "completed",
                iceberg_identifier=req.iceberg_identifier,
                frame=frame,
                fetched_rows=fetched_rows,
                rows_written=fetched_rows,
                symbols=sorted(frame["vt_symbol"].astype(str).unique().tolist()),
                start=str(frame["timestamp"].min()) if not frame.empty else req.start,
                end=str(frame["timestamp"].max()) if not frame.empty else req.end,
                function=req.function,
                interval=req.interval,
                lineage=lineage,
                errors=errors,
            )
            self._emit("debug", "Alpha Vantage history coordination completed", {**base, **result.debug_extras()})
            return result

    def run_intraday_component(
        self,
        req: AlphaVantageIntradayCoordinationRequest,
    ) -> AlphaVantageCoordinationResult:
        base = {
            "request_id": req.component_id,
            "component_id": req.component_id,
            "function": req.function,
            "function_id": req.function_id,
            "ticker": req.ticker,
            "vt_symbol": req.vt_symbol,
            "interval": req.interval,
            "month": req.month,
            "iceberg_identifier": req.iceberg_identifier,
        }
        with self._tracer.start_as_current_span("alpha_vantage.coordinate") as span:
            _set_span_attributes(span, base)
            self._emit("debug", "Alpha Vantage intraday component coordination started", base)
            try:
                payload = self._fetch_intraday(req, base)
                frame = self._normalize_intraday(req, list(getattr(payload, "bars", []) or []), base)
                fetched_rows = int(len(frame))
                frame = self._filter_new_rows(req.iceberg_identifier, frame, base)
                duplicate_rows = fetched_rows - int(len(frame))
                if frame.empty:
                    reason = "no_provider_rows" if fetched_rows == 0 else "no_new_rows_after_dedup"
                    result = AlphaVantageCoordinationResult(
                        status="skipped",
                        iceberg_identifier=req.iceberg_identifier,
                        fetched_rows=fetched_rows,
                        duplicate_rows=duplicate_rows,
                        rows_written=0,
                        symbols=[req.vt_symbol],
                        function=req.function,
                        interval=req.interval,
                        error=reason,
                    )
                    self._emit("debug", "Alpha Vantage intraday component skipped", {**base, **result.debug_extras()})
                    return result
                lineage = self._append_intraday(req, frame, base)
                result = AlphaVantageCoordinationResult(
                    status="completed",
                    iceberg_identifier=req.iceberg_identifier,
                    frame=frame,
                    fetched_rows=fetched_rows,
                    duplicate_rows=duplicate_rows,
                    rows_written=int(len(frame)),
                    symbols=[req.vt_symbol],
                    start=str(frame["timestamp"].min()) if not frame.empty else None,
                    end=str(frame["timestamp"].max()) if not frame.empty else None,
                    function=req.function,
                    interval=req.interval,
                    lineage=lineage,
                )
                self._emit("debug", "Alpha Vantage intraday component completed", {**base, **result.debug_extras()})
                return result
            except AlphaVantagePayloadError as exc:
                result = AlphaVantageCoordinationResult(
                    status="skipped",
                    iceberg_identifier=req.iceberg_identifier,
                    symbols=[req.vt_symbol],
                    function=req.function,
                    interval=req.interval,
                    error=str(exc),
                )
                self._emit("warning", "Alpha Vantage provider rejected intraday component", {**base, **result.debug_extras()})
                return result
            except Exception as exc:  # noqa: BLE001
                logger.exception("Alpha Vantage intraday component coordination failed: %s", req.component_id)
                span.record_exception(exc)
                result = AlphaVantageCoordinationResult(
                    status="failed",
                    iceberg_identifier=req.iceberg_identifier,
                    symbols=[req.vt_symbol],
                    function=req.function,
                    interval=req.interval,
                    error=str(exc),
                )
                self._emit("error", "Alpha Vantage intraday component failed", {**base, **result.debug_extras()})
                return result

    def _fetch_history_symbol(
        self,
        req: AlphaVantageHistoryCoordinationRequest,
        sym: Symbol,
        base: dict[str, Any],
    ) -> tuple[pd.DataFrame | None, dict[str, Any] | None]:
        with self._tracer.start_as_current_span("alpha_vantage.request") as span:
            _set_span_attributes(span, base)
            self._emit("debug", "Alpha Vantage history request started", base)
            try:
                payload = self._request_history_payload(req, sym.ticker)
            except AlphaVantagePayloadError as exc:
                error = {"ticker": sym.ticker, "vt_symbol": sym.vt_symbol, "error": str(exc)}
                self._emit("warning", "Alpha Vantage provider rejected history request", {**base, "error": str(exc)})
                return None, error
            except Exception as exc:  # noqa: BLE001
                span.record_exception(exc)
                self._emit("error", "Alpha Vantage history request failed", {**base, "error": str(exc)})
                raise
            bars = list(getattr(payload, "bars", []) or [])
            frame = _normalize_bars(bars, sym.vt_symbol)
            frame = _filter_range(frame, req.start, req.end)
            if not frame.empty:
                frame["source"] = "alpha_vantage"
                frame["function"] = req.function
            self._emit(
                "debug",
                "Alpha Vantage history request normalized",
                {**base, "fetched_rows": int(len(frame))},
            )
            return frame, None

    def _request_history_payload(self, req: AlphaVantageHistoryCoordinationRequest, ticker: str) -> Any:
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

    def _fetch_intraday(self, req: AlphaVantageIntradayCoordinationRequest, base: dict[str, Any]) -> Any:
        with self._tracer.start_as_current_span("alpha_vantage.request") as span:
            _set_span_attributes(span, base)
            self._emit("debug", "Alpha Vantage intraday request started", base)
            return self.client.timeseries.intraday(
                req.ticker,
                interval=req.interval,
                outputsize=req.outputsize,
                month=req.month,
                adjusted=req.adjusted,
                extended_hours=req.extended_hours,
                entitlement=req.entitlement,
                _cache=req.cache,
                _cache_ttl=req.cache_ttl,
            )

    def _normalize_intraday(
        self,
        req: AlphaVantageIntradayCoordinationRequest,
        bars: list[dict[str, Any]],
        base: dict[str, Any],
    ) -> pd.DataFrame:
        with self._tracer.start_as_current_span("alpha_vantage.normalize") as span:
            _set_span_attributes(span, base)
            frame = _normalize_bars(bars, req.vt_symbol)
            if frame.empty:
                self._emit("debug", "Alpha Vantage intraday normalization returned no rows", {**base, "fetched_rows": 0})
                return frame
            for column in ("open", "high", "low", "close", "adjusted_close", "volume", "dividend_amount", "split_coefficient"):
                if column not in frame.columns:
                    frame[column] = pd.NA
                frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
            frame = frame.drop_duplicates(subset=["vt_symbol", "timestamp"], keep="last")
            frame["source"] = "alpha_vantage"
            frame["provider"] = "alpha_vantage"
            frame["function"] = req.function
            frame["function_id"] = req.function_id
            frame["interval"] = req.interval
            frame["source_month"] = req.month
            frame["request_component_id"] = req.component_id
            frame["ingested_at"] = datetime.now(UTC).replace(tzinfo=None)
            frame = frame.sort_values(["vt_symbol", "timestamp"]).reset_index(drop=True)
            self._emit("debug", "Alpha Vantage intraday rows normalized", {**base, "fetched_rows": int(len(frame))})
            return frame

    def _filter_new_rows(
        self,
        iceberg_identifier: str,
        frame: pd.DataFrame,
        base: dict[str, Any],
    ) -> pd.DataFrame:
        if frame.empty:
            return frame
        with self._tracer.start_as_current_span("alpha_vantage.deduplicate") as span:
            _set_span_attributes(span, base)
            symbols = sorted({str(value) for value in frame["vt_symbol"].astype(str).unique()})
            min_ts = frame["timestamp"].min()
            max_ts = frame["timestamp"].max()
            existing_keys = iceberg_catalog.existing_keys_for_window(
                iceberg_identifier,
                symbols=symbols,
                time_min=min_ts,
                time_max=max_ts,
            )
            if not existing_keys:
                self._emit("debug", "Alpha Vantage intraday dedupe found no existing rows", {**base, "duplicate_rows": 0})
                return frame
            mask = [
                (str(row[0]), row[1]) not in existing_keys
                for row in frame[["vt_symbol", "timestamp"]].itertuples(index=False, name=None)
            ]
            out = frame.loc[mask].reset_index(drop=True)
            self._emit(
                "debug",
                "Alpha Vantage intraday dedupe completed",
                {**base, "duplicate_rows": int(len(frame) - len(out)), "rows_after_dedup": int(len(out))},
            )
            return out

    def _append_history(
        self,
        *,
        req: AlphaVantageHistoryCoordinationRequest,
        frame: pd.DataFrame,
        domain: str,
        meta: AlphaVantageFunction | None,
        partition_spec: list[dict[str, Any]] | None,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        import pyarrow as pa

        arrow = pa.Table.from_pandas(frame, preserve_index=False)
        with self._tracer.start_as_current_span("alpha_vantage.append") as span:
            _set_span_attributes(span, {**base, "rows_written": int(len(frame))})
            iceberg_catalog.append_arrow(
                req.iceberg_identifier,
                arrow,
                properties={
                    "provider": "alpha_vantage",
                    "domain": domain,
                },
                partition_spec=partition_spec,
            )
        catalog_name = (
            f"alpha_vantage.{meta.iceberg_table}" if meta and meta.iceberg_table
            else f"alpha_vantage.{req.table or 'stock_history'}"
        )
        with self._tracer.start_as_current_span("alpha_vantage.register") as span:
            _set_span_attributes(span, {**base, "rows_written": int(len(frame)), "catalog_name": catalog_name})
            lineage = register_dataset_version(
                name=catalog_name,
                provider="alpha_vantage",
                domain=domain,
                df=frame,
                storage_uri=req.iceberg_identifier,
                frequency=req.interval or req.function,
                tags=["alpha_vantage", req.function],
                meta={
                    "symbols": _clean_symbols(req.symbols),
                    "start": req.start,
                    "end": req.end,
                    "function": req.function,
                    "function_id": meta.id if meta else None,
                    "interval": req.interval,
                    "outputsize": req.outputsize,
                    "month": req.month,
                    "adjusted": req.adjusted,
                    "extended_hours": req.extended_hours,
                    "entitlement": req.entitlement,
                    "request_params": req.extra_params,
                    "row_count": int(len(frame)),
                    "symbol_count": int(frame["vt_symbol"].nunique()),
                    "partition_spec": partition_spec,
                },
                file_count=int(frame["vt_symbol"].nunique()),
                iceberg_identifier=req.iceberg_identifier,
                load_mode="managed",
                source_uri=f"alphavantage://{req.function}",
            )
        return lineage

    def _append_intraday(
        self,
        req: AlphaVantageIntradayCoordinationRequest,
        frame: pd.DataFrame,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        import pyarrow as pa

        meta = get_function(req.function_id)
        partition_spec = _partition_spec(meta)
        arrow = pa.Table.from_pandas(frame, preserve_index=False)
        with self._tracer.start_as_current_span("alpha_vantage.append") as span:
            _set_span_attributes(span, {**base, "rows_written": int(len(frame))})
            iceberg_catalog.append_arrow(
                req.iceberg_identifier,
                arrow,
                properties={
                    "provider": "alpha_vantage",
                    "domain": "market.bars.intraday",
                    "interval": req.interval,
                },
                partition_spec=partition_spec,
            )
        with self._tracer.start_as_current_span("alpha_vantage.register") as span:
            _set_span_attributes(span, {**base, "rows_written": int(len(frame))})
            lineage = register_dataset_version(
                name="alpha_vantage.time_series_intraday",
                provider="alpha_vantage",
                domain="market.bars.intraday",
                df=frame,
                storage_uri=req.iceberg_identifier,
                frequency=req.interval,
                tags=["alpha_vantage", "intraday", req.interval],
                meta={
                    "function": req.function,
                    "function_id": req.function_id,
                    "interval": req.interval,
                    "month": req.month,
                    "request_component_id": req.component_id,
                    "source": req.source,
                    "row_count": int(len(frame)),
                    "latest_timestamp": str(frame["timestamp"].max()),
                },
                file_count=1,
                iceberg_identifier=req.iceberg_identifier,
                load_mode="delta",
                source_uri=f"alphavantage://{req.function}?symbol={req.ticker}&month={req.month}&interval={req.interval}",
            )
        return lineage

    def _emit(self, stage: str, message: str, extras: dict[str, Any] | None = None) -> None:
        if self.progress_cb is None:
            return
        try:
            self.progress_cb(stage, message, extras or {})
        except Exception:
            logger.debug("Alpha Vantage progress callback failed", exc_info=True)


def _resolve_function_metadata(function: str) -> AlphaVantageFunction | None:
    key = (function or "").strip().lower()
    function_id = _FUNCTION_TO_ID.get(key, key)
    return get_function(function_id)


def _partition_spec(meta: AlphaVantageFunction | None) -> list[dict[str, Any]] | None:
    return [field.to_dict() for field in meta.partition_spec] if meta and meta.partition_spec else None


def _clean_symbols(symbols: list[str]) -> list[str]:
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
    return frame[keep].dropna(subset=["timestamp", "open", "high", "low", "close"])


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


def _request_id(*parts: Any) -> str:
    return ":".join(str(part) for part in parts if part is not None)


def _set_span_attributes(span: Any, values: dict[str, Any]) -> None:
    for key, value in values.items():
        if value is None:
            continue
        try:
            span.set_attribute(f"aqp.{key}", value)
        except Exception:
            pass


__all__ = [
    "AlphaVantageCoordinationResult",
    "AlphaVantageHistoryCoordinationRequest",
    "AlphaVantageIntradayCoordinationRequest",
    "AlphaVantageRequestCoordinator",
    "ProgressCallback",
]
