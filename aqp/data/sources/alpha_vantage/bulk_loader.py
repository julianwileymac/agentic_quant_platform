"""Multi-endpoint bulk loader for AlphaVantage into the per-endpoint Iceberg lake.

Drives the configured `:class:`aqp.data.sources.alpha_vantage.catalog.AlphaVantageFunction`
descriptors:

1. Resolve the symbol set (`"all_active"` -> Instrument table, or explicit list).
2. Iterate `(symbol, endpoint)` pairs, calling the right ``AlphaVantageClient``
   method per endpoint.
3. Normalize to a canonical ``pyarrow.Table`` per endpoint.
4. Append into the matching Iceberg table using the endpoint's partition spec
   via :func:`aqp.data.iceberg_catalog.append_arrow`.
5. Register lineage with :func:`aqp.data.catalog.register_dataset_version`
   and emit :class:`DataLink` rows so coverage queries light up.

The loader is intentionally synchronous within the worker; it leans on the
existing :class:`AlphaVantageClient` rate limiter so it stays under the
configured RPM/daily quota across long runs. Progress is reported via the
shared `aqp.tasks._progress.emit*` helpers.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from aqp.core.types import Symbol
from aqp.data import iceberg_catalog
from aqp.data.catalog import register_dataset_version
from aqp.data.sources.alpha_vantage.catalog import (
    AlphaVantageFunction,
    get_function,
)
from aqp.data.sources.alpha_vantage.client import AlphaVantageClient
from aqp.persistence.db import get_session
from aqp.persistence.models import DataLink, Instrument

logger = logging.getLogger(__name__)


@dataclass
class BulkLoadEndpointResult:
    function_id: str
    iceberg_identifier: str | None
    rows_written: int = 0
    symbols_loaded: int = 0
    symbols_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    lineage: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_id": self.function_id,
            "iceberg_identifier": self.iceberg_identifier,
            "rows_written": int(self.rows_written),
            "symbols_loaded": int(self.symbols_loaded),
            "symbols_skipped": int(self.symbols_skipped),
            "errors": list(self.errors),
            "lineage": dict(self.lineage),
        }


@dataclass
class BulkLoadResult:
    requested_symbols: int
    requested_endpoints: list[str]
    started_at: str
    finished_at: str | None = None
    total_rows: int = 0
    endpoints: list[BulkLoadEndpointResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_symbols": int(self.requested_symbols),
            "requested_endpoints": list(self.requested_endpoints),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_rows": int(self.total_rows),
            "endpoints": [entry.to_dict() for entry in self.endpoints],
        }


ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


def _noop_progress(stage: str, message: str, extras: dict[str, Any] | None = None) -> None:  # noqa: ARG001
    return None


def resolve_symbols(
    symbols: Iterable[str] | str,
    *,
    filters: dict[str, Any] | None = None,
    limit: int | None = None,
) -> list[str]:
    """Resolve the input to a concrete ``vt_symbol`` list.

    ``symbols == "all_active"`` reads every active row from the
    :class:`Instrument` table (paged via ``limit``); otherwise the iterable
    is normalized in-place. ``filters`` accepts ``exchange``, ``asset_class``,
    or ``security_type`` lists to narrow the active universe.
    """
    if isinstance(symbols, str) and symbols.strip().lower() in {"all_active", "all", "*"}:
        return _query_active_universe(filters=filters, limit=limit)
    if isinstance(symbols, str):
        return [_normalize(symbols)]
    return [_normalize(s) for s in symbols if str(s or "").strip()]


def _query_active_universe(
    *,
    filters: dict[str, Any] | None,
    limit: int | None,
) -> list[str]:
    filters = filters or {}
    with get_session() as session:
        stmt = select(Instrument.vt_symbol).where(Instrument.is_active.is_(True))
        exchanges = filters.get("exchange") or filters.get("exchanges")
        if exchanges:
            stmt = stmt.where(Instrument.exchange.in_([str(x).upper() for x in exchanges]))
        asset_classes = filters.get("asset_class") or filters.get("asset_classes")
        if asset_classes:
            stmt = stmt.where(Instrument.asset_class.in_([str(x).lower() for x in asset_classes]))
        security_types = filters.get("security_type") or filters.get("security_types")
        if security_types:
            stmt = stmt.where(Instrument.security_type.in_([str(x).lower() for x in security_types]))
        stmt = stmt.order_by(Instrument.ticker.asc())
        if limit and int(limit) > 0:
            stmt = stmt.limit(int(limit))
        rows = session.execute(stmt).scalars().all()
    return [str(vt_symbol) for vt_symbol in rows if vt_symbol]


def _normalize(raw: str) -> str:
    raw = str(raw or "").strip().upper()
    if not raw:
        return raw
    if "." in raw:
        return raw
    return f"{raw}.NASDAQ"


class AlphaVantageBulkLoader:
    """Drive a multi-endpoint AlphaVantage materialization."""

    def __init__(
        self,
        *,
        client: AlphaVantageClient | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self.client = client or AlphaVantageClient()
        self._owns_client = client is None
        self.progress_cb = progress_cb or _noop_progress

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        endpoints: list[str],
        symbols: list[str] | str,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        cache: bool = True,
        cache_ttl: float | None = None,
    ) -> BulkLoadResult:
        started_at = datetime.now(UTC).isoformat()
        symbol_list = resolve_symbols(symbols, filters=filters, limit=limit)
        endpoint_specs = [
            spec for spec in (get_function(eid) for eid in endpoints) if spec is not None
        ]
        result = BulkLoadResult(
            requested_symbols=len(symbol_list),
            requested_endpoints=[entry.id for entry in endpoint_specs],
            started_at=started_at,
        )

        self.progress_cb(
            "started",
            f"Bulk load: {len(endpoint_specs)} endpoint(s) x {len(symbol_list)} symbol(s)",
            {"endpoints": result.requested_endpoints, "symbols": len(symbol_list)},
        )

        for endpoint in endpoint_specs:
            entry = self._run_endpoint(
                endpoint,
                symbol_list,
                cache=cache,
                cache_ttl=cache_ttl,
            )
            result.endpoints.append(entry)
            result.total_rows += entry.rows_written

        result.finished_at = datetime.now(UTC).isoformat()
        self.progress_cb(
            "completed",
            f"Bulk load complete: {result.total_rows} rows across {len(endpoint_specs)} endpoint(s)",
            {"total_rows": result.total_rows},
        )
        return result

    # ------------------------------------------------------------------
    # Per-endpoint
    # ------------------------------------------------------------------

    def _run_endpoint(
        self,
        endpoint: AlphaVantageFunction,
        symbols: list[str],
        *,
        cache: bool,
        cache_ttl: float | None,
    ) -> BulkLoadEndpointResult:
        identifier = endpoint.iceberg_identifier
        result = BulkLoadEndpointResult(
            function_id=endpoint.id,
            iceberg_identifier=identifier,
        )
        if not endpoint.lake_supported or identifier is None:
            result.errors.append("endpoint not lake-supported")
            return result

        chunks: list[pd.DataFrame] = []
        for index, vt_symbol in enumerate(symbols, start=1):
            sym = Symbol.parse(vt_symbol)
            self.progress_cb(
                "running",
                f"{endpoint.id}: fetching {vt_symbol} ({index}/{len(symbols)})",
                {
                    "endpoint": endpoint.id,
                    "vt_symbol": vt_symbol,
                    "index": index,
                    "total": len(symbols),
                },
            )
            try:
                payload = self._fetch_for_endpoint(
                    endpoint,
                    sym,
                    cache=cache,
                    cache_ttl=cache_ttl,
                )
                frame = self._normalize_payload(endpoint, sym, payload)
            except Exception as exc:  # noqa: BLE001
                logger.exception("bulk loader failed for %s.%s", endpoint.id, vt_symbol)
                result.errors.append(f"{vt_symbol}: {exc}")
                result.symbols_skipped += 1
                continue
            if frame is None or frame.empty:
                result.symbols_skipped += 1
                continue
            chunks.append(frame)
            result.symbols_loaded += 1

        if not chunks:
            self.progress_cb(
                "endpoint-done",
                f"{endpoint.id}: no rows produced",
                {"endpoint": endpoint.id},
            )
            return result

        combined = pd.concat(chunks, ignore_index=True)
        if endpoint.timestamp_column and endpoint.timestamp_column in combined.columns:
            combined = combined.sort_values([endpoint.symbol_column or "vt_symbol", endpoint.timestamp_column])
        combined = combined.reset_index(drop=True)
        result.rows_written = int(len(combined))

        self._materialize(endpoint, combined, result)
        return result

    def _materialize(
        self,
        endpoint: AlphaVantageFunction,
        frame: pd.DataFrame,
        result: BulkLoadEndpointResult,
    ) -> None:
        import pyarrow as pa

        arrow = pa.Table.from_pandas(frame, preserve_index=False)
        partition_spec = (
            [field.to_dict() for field in endpoint.partition_spec]
            if endpoint.partition_spec
            else None
        )
        iceberg_catalog.append_arrow(
            endpoint.iceberg_identifier,
            arrow,
            properties={
                "provider": "alpha_vantage",
                "domain": endpoint.domain,
                "function_id": endpoint.id,
            },
            partition_spec=partition_spec,
        )
        try:
            lineage = register_dataset_version(
                name=f"alpha_vantage.{endpoint.iceberg_table}",
                provider="alpha_vantage",
                domain=endpoint.domain,
                df=frame,
                storage_uri=endpoint.iceberg_identifier,
                frequency=endpoint.id,
                tags=["alpha_vantage", endpoint.category, endpoint.id],
                meta={
                    "function_id": endpoint.id,
                    "row_count": int(len(frame)),
                    "symbol_count": int(frame["vt_symbol"].nunique())
                    if "vt_symbol" in frame.columns
                    else 0,
                    "partition_spec": partition_spec,
                },
                file_count=int(frame["vt_symbol"].nunique()) if "vt_symbol" in frame.columns else 1,
                iceberg_identifier=endpoint.iceberg_identifier,
                load_mode="managed",
                source_uri=f"alphavantage://{endpoint.function}",
            )
        except Exception:  # noqa: BLE001
            lineage = {}
            logger.warning("lineage registration skipped for %s", endpoint.id, exc_info=True)
        result.lineage = lineage

        emitted = self._emit_data_links(endpoint, frame, lineage)
        self.progress_cb(
            "endpoint-done",
            f"{endpoint.id}: wrote {result.rows_written} rows, linked {emitted} instrument(s)",
            {
                "endpoint": endpoint.id,
                "rows": result.rows_written,
                "data_links": emitted,
            },
        )

    def _emit_data_links(
        self,
        endpoint: AlphaVantageFunction,
        frame: pd.DataFrame,
        lineage: dict[str, Any],
    ) -> int:
        version_id = lineage.get("dataset_version_id")
        if not version_id or "vt_symbol" not in frame.columns:
            return 0
        symbols = sorted({str(s) for s in frame["vt_symbol"].astype(str).unique() if s})
        if not symbols:
            return 0
        ts_col = endpoint.timestamp_column or "timestamp"
        coverage_start = None
        coverage_end = None
        if ts_col in frame.columns and not frame[ts_col].dropna().empty:
            coverage_start = pd.to_datetime(frame[ts_col]).min().to_pydatetime()
            coverage_end = pd.to_datetime(frame[ts_col]).max().to_pydatetime()

        emitted = 0
        with get_session() as session:
            instrument_rows = session.execute(
                select(Instrument).where(Instrument.vt_symbol.in_(symbols))
            ).scalars().all()
            instrument_by_vt = {row.vt_symbol: row for row in instrument_rows}

            for vt_symbol in symbols:
                instrument = instrument_by_vt.get(vt_symbol)
                instrument_id = instrument.id if instrument else None
                row_count = int((frame["vt_symbol"] == vt_symbol).sum())
                link = DataLink(
                    dataset_version_id=version_id,
                    entity_kind="instrument",
                    entity_id=str(instrument_id or vt_symbol),
                    instrument_id=instrument_id,
                    coverage_start=coverage_start,
                    coverage_end=coverage_end,
                    row_count=row_count,
                    meta={
                        "function_id": endpoint.id,
                        "iceberg_identifier": endpoint.iceberg_identifier,
                        "vt_symbol": vt_symbol,
                    },
                )
                session.add(link)
                emitted += 1
            session.flush()
        return emitted

    # ------------------------------------------------------------------
    # Endpoint dispatch
    # ------------------------------------------------------------------

    def _fetch_for_endpoint(
        self,
        endpoint: AlphaVantageFunction,
        symbol: Symbol,
        *,
        cache: bool,
        cache_ttl: float | None,
    ) -> Any:
        ticker = symbol.ticker
        options = {"_cache": cache, "_cache_ttl": cache_ttl}
        ts = self.client.timeseries
        f = self.client.fundamentals
        intel = self.client.intelligence
        tech = self.client.technicals
        if endpoint.id == "timeseries.intraday":
            return ts.intraday(ticker, interval="5min", outputsize="full", **options)
        if endpoint.id == "timeseries.daily":
            return ts.daily(ticker, outputsize="full", **options)
        if endpoint.id == "timeseries.daily_adjusted":
            return ts.daily_adjusted(ticker, outputsize="full", **options)
        if endpoint.id == "timeseries.weekly_adjusted":
            return ts.weekly_adjusted(ticker, **options)
        if endpoint.id == "timeseries.monthly_adjusted":
            return ts.monthly_adjusted(ticker, **options)
        if endpoint.id == "fundamentals.overview":
            return f.overview(ticker)
        if endpoint.id == "fundamentals.income_statement":
            return f.income_statement(ticker)
        if endpoint.id == "fundamentals.balance_sheet":
            return f.balance_sheet(ticker)
        if endpoint.id == "fundamentals.cash_flow":
            return f.cash_flow(ticker)
        if endpoint.id == "fundamentals.earnings":
            return f.earnings(ticker)
        if endpoint.id == "fundamentals.dividends":
            return f.dividends(ticker)
        if endpoint.id == "fundamentals.splits":
            return f.splits(ticker)
        if endpoint.id == "fundamentals.listing":
            return self.client.listing_status()
        if endpoint.id == "intelligence.news":
            return intel.news(tickers=ticker, limit=50)
        if endpoint.id == "intelligence.top_movers":
            return intel.top_movers()
        if endpoint.id == "intelligence.insider":
            return intel.insider(ticker)
        if endpoint.id == "technicals.sma":
            return tech.get("SMA", ticker, interval="daily", time_period=20, series_type="close")
        if endpoint.id == "technicals.rsi":
            return tech.get("RSI", ticker, interval="daily", time_period=14, series_type="close")
        raise ValueError(f"unsupported endpoint: {endpoint.id}")

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    def _normalize_payload(
        self,
        endpoint: AlphaVantageFunction,
        symbol: Symbol,
        payload: Any,
    ) -> pd.DataFrame:
        if endpoint.category == "timeseries":
            return _frame_from_bars(getattr(payload, "bars", []) or [], symbol)
        if endpoint.id == "intelligence.top_movers":
            return _frame_from_top_movers(payload, as_of=time.time())
        if endpoint.id == "intelligence.news":
            return _frame_from_news(payload, default_symbol=symbol)
        if endpoint.id == "intelligence.insider":
            return _frame_from_rows(payload, symbol)
        if endpoint.id == "fundamentals.dividends":
            return _frame_from_rows(payload, symbol)
        if endpoint.id == "fundamentals.splits":
            return _frame_from_rows(payload, symbol)
        if endpoint.category == "technicals":
            return _frame_from_indicator_payload(payload, symbol)
        if endpoint.category == "fundamentals":
            return _frame_from_object_payload(payload, symbol)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Frame helpers
# ---------------------------------------------------------------------------


def _frame_from_bars(bars: list[dict[str, Any]], symbol: Symbol) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame()
    frame = pd.DataFrame(bars)
    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    if "timestamp" not in frame.columns:
        return pd.DataFrame()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
    frame["timestamp"] = frame["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None).astype(
        "datetime64[us]"
    )
    for column in (
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["vt_symbol"] = symbol.vt_symbol
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
    for column in keep:
        if column not in frame.columns:
            frame[column] = None
    frame = frame[keep].dropna(subset=["timestamp", "open", "high", "low", "close"])
    return frame.reset_index(drop=True)


def _frame_from_object_payload(payload: Any, symbol: Symbol) -> pd.DataFrame:
    """Generic object payload (Overview, statements) flattened into one row."""
    if payload is None:
        return pd.DataFrame()
    raw: dict[str, Any]
    if hasattr(payload, "model_dump"):
        raw = dict(payload.model_dump())
    elif isinstance(payload, dict):
        raw = dict(payload)
        if "annual" in raw or "quarterly" in raw:
            raw = {
                "annual": raw.get("annual"),
                "quarterly": raw.get("quarterly"),
                "symbol": raw.get("symbol"),
            }
    else:
        raw = {}
    if not raw:
        return pd.DataFrame()
    row = {
        "vt_symbol": symbol.vt_symbol,
        "as_of": pd.Timestamp.utcnow().to_datetime64().astype("datetime64[us]"),
        "payload": raw,
    }
    return pd.DataFrame([row])


def _frame_from_rows(payload: Any, symbol: Symbol) -> pd.DataFrame:
    if payload is None:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    iterable = payload if isinstance(payload, list) else getattr(payload, "data", payload)
    if not isinstance(iterable, list):
        return pd.DataFrame()
    for entry in iterable:
        if hasattr(entry, "model_dump"):
            rows.append(dict(entry.model_dump()))
        elif isinstance(entry, dict):
            rows.append(dict(entry))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["vt_symbol"] = symbol.vt_symbol
    return frame


def _frame_from_news(payload: Any, default_symbol: Symbol) -> pd.DataFrame:
    if payload is None:
        return pd.DataFrame()
    body = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
    feed = body.get("feed") or []
    if not isinstance(feed, list):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for entry in feed:
        if not isinstance(entry, dict):
            continue
        ts_raw = entry.get("time_published") or entry.get("timestamp")
        ts = pd.to_datetime(ts_raw, errors="coerce", utc=True)
        if pd.isna(ts):
            ts = pd.Timestamp.utcnow()
        ts = pd.to_datetime(ts, utc=True).tz_convert("UTC").tz_localize(None).to_datetime64().astype(
            "datetime64[us]"
        )
        related: list[str] = []
        for tk in entry.get("ticker_sentiment") or []:
            if isinstance(tk, dict) and tk.get("ticker"):
                related.append(str(tk["ticker"]).upper())
        if not related:
            related.append(default_symbol.ticker)
        for ticker in related:
            rows.append(
                {
                    "vt_symbol": Symbol.parse(f"{ticker}.{default_symbol.exchange.value}").vt_symbol,
                    "timestamp": ts,
                    "title": entry.get("title"),
                    "url": entry.get("url"),
                    "source": entry.get("source"),
                    "summary": entry.get("summary"),
                    "overall_sentiment_score": entry.get("overall_sentiment_score"),
                    "relevance_score": entry.get("relevance_score"),
                    "topics": entry.get("topics"),
                }
            )
    return pd.DataFrame(rows)


def _frame_from_top_movers(payload: Any, *, as_of: float) -> pd.DataFrame:
    body = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload or {})
    rows: list[dict[str, Any]] = []
    for bucket in ("top_gainers", "top_losers", "most_actively_traded"):
        for entry in body.get(bucket) or []:
            if not isinstance(entry, dict):
                continue
            ticker = str(entry.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            rows.append(
                {
                    "vt_symbol": Symbol.parse(ticker).vt_symbol,
                    "as_of": pd.Timestamp.utcfromtimestamp(as_of).to_datetime64().astype(
                        "datetime64[us]"
                    ),
                    "bucket": bucket,
                    "price": entry.get("price"),
                    "change_amount": entry.get("change_amount"),
                    "change_percentage": entry.get("change_percentage"),
                    "volume": entry.get("volume"),
                }
            )
    return pd.DataFrame(rows)


def _frame_from_indicator_payload(payload: Any, symbol: Symbol) -> pd.DataFrame:
    body: dict[str, Any]
    if hasattr(payload, "model_dump"):
        body = dict(payload.model_dump())
    elif isinstance(payload, dict):
        body = dict(payload)
    else:
        return pd.DataFrame()
    series_key = next((k for k in body if isinstance(body.get(k), dict) and "Technical" in k), None)
    series = body.get(series_key) if series_key else None
    if not isinstance(series, dict):
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for ts_raw, fields in series.items():
        if not isinstance(fields, dict):
            continue
        ts = pd.to_datetime(ts_raw, errors="coerce", utc=True)
        if pd.isna(ts):
            continue
        ts = ts.tz_convert("UTC").tz_localize(None).to_datetime64().astype("datetime64[us]")
        row = {"vt_symbol": symbol.vt_symbol, "timestamp": ts}
        for key, value in fields.items():
            try:
                row[key.lower()] = float(value)
            except (TypeError, ValueError):
                row[key.lower()] = value
        rows.append(row)
    return pd.DataFrame(rows)


__all__ = [
    "AlphaVantageBulkLoader",
    "BulkLoadEndpointResult",
    "BulkLoadResult",
    "ProgressCallback",
    "resolve_symbols",
]
