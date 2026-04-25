"""Technical snapshot tool — hands the trader crew a compact indicator sheet.

Given a ``vt_symbol`` and as-of date this tool reads the last ~60 bars
from the Parquet lake (via DuckDB) and computes RSI-14, MACD(12,26,9),
Bollinger(20,2), SMA-20/50, ATR-14 using the incremental indicator
classes in :mod:`aqp.core.indicators`. Returns a CSV-like snapshot the
Technical Analyst role can reason over.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

import pandas as pd
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from aqp.core.indicators import (
    AverageTrueRange,
    BollingerBands,
    ExponentialMovingAverage,
    MovingAverageConvergenceDivergence,
    RelativeStrengthIndex,
    SimpleMovingAverage,
)
from aqp.data.duckdb_engine import get_connection

logger = logging.getLogger(__name__)


class TechnicalInput(BaseModel):
    vt_symbol: str = Field(..., description="Canonical vt_symbol (e.g. AAPL.NASDAQ)")
    as_of: str | None = Field(
        default=None,
        description="ISO date string; defaults to today UTC",
    )
    lookback_days: int = Field(default=120, description="Trailing bar window for warm-up")


def _to_float(x: float | int | None) -> float:
    if x is None:
        return float("nan")
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _format_snapshot(rows: dict[str, float]) -> str:
    """Pretty print a dict of `name -> value` as CSV key/value rows."""

    def _fmt(v: float) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""
        return f"{v:.4f}"

    lines = ["indicator,value"]
    for k, v in rows.items():
        lines.append(f"{k},{_fmt(v)}")
    return "\n".join(lines)


def compute_technical_snapshot(
    vt_symbol: str,
    as_of: datetime | str | None = None,
    lookback_days: int = 120,
) -> dict[str, float]:
    """Compute a compact indicator snapshot for ``(vt_symbol, as_of)``.

    Independently useful: called by :class:`TechnicalTool` (for the LLM)
    and :class:`aqp.agents.trading.decision_cache.DecisionCache`'s
    context-hash builder.
    """
    if as_of is None:
        as_of_dt = datetime.utcnow()
    elif isinstance(as_of, str):
        as_of_dt = pd.to_datetime(as_of).to_pydatetime()
    else:
        as_of_dt = as_of
    start = as_of_dt - timedelta(days=lookback_days)

    conn = get_connection()
    try:
        df = conn.execute(
            """
            SELECT timestamp, open, high, low, close, volume
            FROM bars
            WHERE vt_symbol = ? AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
            """,
            [vt_symbol, start, as_of_dt],
        ).fetchdf()
    finally:
        conn.close()

    if df.empty:
        return {}

    rsi = RelativeStrengthIndex(14)
    macd = MovingAverageConvergenceDivergence(12, 26, 9)
    bb = BollingerBands(20, 2.0)
    sma20 = SimpleMovingAverage(20)
    sma50 = SimpleMovingAverage(50)
    ema12 = ExponentialMovingAverage(12)
    atr = AverageTrueRange(14)

    last_close = float("nan")
    for _, row in df.iterrows():
        price = float(row["close"])
        # indicator update signatures accept a single numeric value.
        rsi.update(price)
        macd.update(price)
        bb.update(price)
        sma20.update(price)
        sma50.update(price)
        ema12.update(price)
        # ATR wants full BarData-like fields; build a dict-adapter.
        try:
            from aqp.core.types import BarData, Interval, Symbol

            sym = _safe_symbol(vt_symbol)
            bar = BarData(
                symbol=sym,
                timestamp=row["timestamp"].to_pydatetime()
                if hasattr(row["timestamp"], "to_pydatetime")
                else row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=price,
                volume=float(row["volume"]),
                interval=Interval.DAY,
            )
            atr.update(bar)
        except Exception:  # pragma: no cover - defensive
            pass
        last_close = price

    snapshot: dict[str, float] = {
        "close": last_close,
        "sma_20": _to_float(sma20.current),
        "sma_50": _to_float(sma50.current),
        "ema_12": _to_float(ema12.current),
        "rsi_14": _to_float(rsi.current),
        "macd": _to_float(getattr(macd, "current", float("nan"))),
        "macd_signal": _to_float(getattr(macd, "signal_value", float("nan"))),
        "macd_histogram": _to_float(getattr(macd, "histogram", float("nan"))),
        "bb_upper": _to_float(getattr(bb, "upper", float("nan"))),
        "bb_middle": _to_float(getattr(bb, "middle", float("nan"))),
        "bb_lower": _to_float(getattr(bb, "lower", float("nan"))),
        "atr_14": _to_float(getattr(atr, "current", float("nan"))),
    }
    return snapshot


def _safe_symbol(vt_symbol: str):
    from aqp.core.types import Symbol

    try:
        return Symbol.parse(vt_symbol)
    except Exception:  # pragma: no cover
        return Symbol(ticker=vt_symbol)


class TechnicalTool(BaseTool):
    name: str = "technical_snapshot"
    description: str = (
        "Return a compact technical indicator snapshot (RSI, MACD, Bollinger, "
        "SMA-20/50, ATR) for a given vt_symbol as-of a date. Output is a "
        "CSV-style 'indicator,value' table suitable for an analyst prompt."
    )
    args_schema: type[BaseModel] = TechnicalInput

    def _run(  # type: ignore[override]
        self,
        vt_symbol: str,
        as_of: str | None = None,
        lookback_days: int = 120,
    ) -> str:
        snapshot = compute_technical_snapshot(vt_symbol, as_of, lookback_days)
        if not snapshot:
            return f"No bars found for {vt_symbol} as-of {as_of or 'today'}."
        return _format_snapshot(snapshot)
