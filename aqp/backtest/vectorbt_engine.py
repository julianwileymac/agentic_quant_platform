"""Vectorbt-backed backtest engine.

Adapter that runs an :class:`IAlphaModel` against a historical bars frame via
``vectorbt.Portfolio.from_signals`` and returns an
:class:`aqp.backtest.engine.BacktestResult` so the rest of the platform
(runner, persistence, MLflow wiring, UI) does not need to know which engine
produced the result.

Usage (YAML)::

    backtest:
      class: VectorbtEngine
      kwargs:
        initial_cash: 100000
        fees: 0.001
        slippage: 0.0005
        allow_short: true

Only the alpha stage of the 5-stage Framework is consumed: the engine turns
signals into boolean ``entries`` / ``exits`` per-symbol matrices and lets
vectorbt handle capital allocation. For the full Lean 5-stage pipeline use
:class:`aqp.backtest.engine.EventDrivenBacktester` instead.

Reference: https://vectorbt.dev/ (`vectorbt.portfolio.base.Portfolio`).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise
from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import register
from aqp.core.types import Direction, Symbol

logger = logging.getLogger(__name__)


def _import_vbt():
    """Lazy import guard — vectorbt triggers a heavy numba compile."""
    try:
        import vectorbt as vbt
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "vectorbt is not installed. Install with `pip install -e \".[vectorbt]\"`"
        ) from e
    return vbt


def _pivot_close(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    pivot = df.pivot_table(
        index="timestamp", columns="vt_symbol", values="close", aggfunc="last"
    )
    return pivot.sort_index().ffill()


def _resolve_alpha(strategy: IAlphaModel | IStrategy) -> IAlphaModel:
    """Return the alpha stage of a framework algorithm, or the strategy itself
    if it already implements :class:`IAlphaModel`."""
    if hasattr(strategy, "alpha_model"):
        return strategy.alpha_model  # type: ignore[attr-defined]
    return strategy  # type: ignore[return-value]


def _universe_from_bars(bars: pd.DataFrame) -> list[Symbol]:
    return [Symbol.parse(v) for v in bars["vt_symbol"].unique()]


@register("VectorbtEngine")
class VectorbtEngine:
    """Vectorized backtest engine backed by ``vectorbt``.

    The engine replays a strategy's :meth:`IAlphaModel.generate_signals` over a
    rolling history up to each timestamp and records the resulting long/short
    decisions as boolean ``entries`` / ``exits`` matrices, which are then fed
    into ``vbt.Portfolio.from_signals``.
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        fees: float = 0.0005,
        slippage: float = 0.0002,
        allow_short: bool = True,
        freq: str = "1D",
        group_by: bool = False,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        warmup_bars: int = 30,
    ) -> None:
        self.initial_cash = float(initial_cash)
        self.fees = float(fees)
        self.slippage = float(slippage)
        self.allow_short = bool(allow_short)
        self.freq = str(freq)
        self.group_by = bool(group_by)
        self.start = pd.Timestamp(start) if start else None
        self.end = pd.Timestamp(end) if end else None
        self.warmup_bars = int(warmup_bars)

    def run(self, strategy: IAlphaModel | IStrategy, bars: pd.DataFrame) -> BacktestResult:
        if bars.empty:
            raise ValueError("VectorbtEngine: bars frame is empty.")
        vbt = _import_vbt()

        frame = bars.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        if self.start is not None:
            frame = frame[frame["timestamp"] >= self.start]
        if self.end is not None:
            frame = frame[frame["timestamp"] <= self.end]
        if frame.empty:
            raise ValueError("VectorbtEngine: no bars remain after date filter.")

        close = _pivot_close(frame)
        entries = pd.DataFrame(False, index=close.index, columns=close.columns)
        exits = pd.DataFrame(False, index=close.index, columns=close.columns)
        short_entries = pd.DataFrame(False, index=close.index, columns=close.columns)
        short_exits = pd.DataFrame(False, index=close.index, columns=close.columns)

        alpha = _resolve_alpha(strategy)
        universe = _universe_from_bars(frame)
        state: dict[str, Direction] = {}

        sorted_frame = frame.sort_values(["timestamp", "vt_symbol"]).reset_index(drop=True)
        history_mask = pd.Series(False, index=sorted_frame.index)
        ts_index = close.index

        for i, ts in enumerate(ts_index):
            if i < self.warmup_bars:
                continue
            day_mask = sorted_frame["timestamp"] == ts
            history_mask |= day_mask
            history_view = sorted_frame[history_mask]
            ctx: dict[str, Any] = {"current_time": ts.to_pydatetime()}
            try:
                signals = alpha.generate_signals(history_view, universe, ctx)
            except Exception:  # pragma: no cover - defensive
                logger.exception("alpha.generate_signals failed at %s", ts)
                continue

            # Track long/short state per symbol.
            for sig in signals:
                vt = sig.symbol.vt_symbol
                if vt not in close.columns:
                    continue
                current = state.get(vt)
                if sig.direction == Direction.LONG:
                    if current != Direction.LONG:
                        entries.at[ts, vt] = True
                        if current == Direction.SHORT:
                            short_exits.at[ts, vt] = True
                        state[vt] = Direction.LONG
                elif sig.direction == Direction.SHORT and self.allow_short:
                    if current != Direction.SHORT:
                        short_entries.at[ts, vt] = True
                        if current == Direction.LONG:
                            exits.at[ts, vt] = True
                        state[vt] = Direction.SHORT
                elif sig.direction == Direction.NET:
                    if current == Direction.LONG:
                        exits.at[ts, vt] = True
                    elif current == Direction.SHORT:
                        short_exits.at[ts, vt] = True
                    state[vt] = Direction.NET

        # Build the Portfolio. When shorts are not allowed, fall back to the
        # simpler long-only signature for speed.
        init_cash = self.initial_cash
        try:
            if self.allow_short and (short_entries.any().any() or short_exits.any().any()):
                pf = vbt.Portfolio.from_signals(
                    close=close,
                    entries=entries,
                    exits=exits,
                    short_entries=short_entries,
                    short_exits=short_exits,
                    init_cash=init_cash,
                    fees=self.fees,
                    slippage=self.slippage,
                    freq=self.freq,
                    group_by=self.group_by,
                    cash_sharing=self.group_by,
                )
            else:
                pf = vbt.Portfolio.from_signals(
                    close=close,
                    entries=entries,
                    exits=exits,
                    init_cash=init_cash,
                    fees=self.fees,
                    slippage=self.slippage,
                    freq=self.freq,
                    group_by=self.group_by,
                    cash_sharing=self.group_by,
                )
        except Exception:  # pragma: no cover
            logger.exception("vbt.Portfolio.from_signals failed")
            raise

        return _to_backtest_result(pf, close, self.initial_cash)


def _to_backtest_result(pf: Any, close: pd.DataFrame, initial_cash: float) -> BacktestResult:
    """Translate a ``vbt.Portfolio`` into an :class:`BacktestResult`."""
    # Equity: portfolio value at portfolio level (sum across columns/groups).
    try:
        value = pf.value()
    except Exception:
        value = pf.total_value()
    if isinstance(value, pd.DataFrame):
        equity = value.sum(axis=1)
    else:
        equity = value
    equity = equity.astype(float)
    equity.name = "equity"
    equity = equity.sort_index()

    # Normalise to start at `initial_cash` so summarise() yields the
    # conventional total-return interpretation.
    if len(equity):
        first = float(equity.iloc[0])
        if first == 0.0:
            equity = equity + initial_cash
        elif abs(first - initial_cash) > 1e-6:
            equity = equity / first * initial_cash

    # Trades table (records_readable is a user-friendly DataFrame).
    try:
        trades_df = pf.trades.records_readable.copy()
    except Exception:
        trades_df = pd.DataFrame()
    if not trades_df.empty:
        col_map = {
            "Entry Timestamp": "timestamp",
            "Exit Timestamp": "exit_timestamp",
            "Entry Idx": "entry_idx",
            "Exit Idx": "exit_idx",
            "Column": "vt_symbol",
            "Size": "quantity",
            "Entry Price": "price",
            "Exit Price": "exit_price",
            "Direction": "side",
            "Fees": "commission",
            "PnL": "pnl",
            "Return": "return",
        }
        trades_df = trades_df.rename(columns={k: v for k, v in col_map.items() if k in trades_df.columns})
        if "side" in trades_df.columns:
            trades_df["side"] = trades_df["side"].astype(str).str.lower().map(
                lambda s: "buy" if "long" in s else ("sell" if "short" in s else s)
            )
        for missing in ("slippage", "strategy_id"):
            if missing not in trades_df.columns:
                trades_df[missing] = 0.0 if missing == "slippage" else ""

    # Orders table.
    try:
        orders_df = pf.orders.records_readable.copy()
    except Exception:
        orders_df = pd.DataFrame()
    if not orders_df.empty:
        orders_df = orders_df.rename(
            columns={
                "Order Id": "order_id",
                "Column": "vt_symbol",
                "Timestamp": "created_at",
                "Side": "side",
                "Size": "quantity",
                "Price": "price",
                "Fees": "fees",
            }
        )
        if "side" in orders_df.columns:
            orders_df["side"] = orders_df["side"].astype(str).str.lower()
        orders_df["status"] = "filled"

    summary = summarise(equity, trades_df if not trades_df.empty else None)
    summary["engine"] = "vectorbt"

    first_ts = equity.index[0] if len(equity) else None
    last_ts = equity.index[-1] if len(equity) else None

    return BacktestResult(
        equity_curve=equity,
        trades=trades_df,
        orders=orders_df,
        tickets=[],
        summary=summary,
        start=first_ts.to_pydatetime() if first_ts is not None else None,
        end=last_ts.to_pydatetime() if last_ts is not None else None,
        initial_cash=float(initial_cash),
        final_equity=float(equity.iloc[-1]) if len(equity) else float(initial_cash),
    )


def run_vectorized_signals(
    close: pd.DataFrame,
    entries: pd.DataFrame,
    exits: pd.DataFrame,
    init_cash: float = 100000.0,
    fees: float = 0.001,
    slippage: float = 0.0,
    freq: str = "1D",
) -> BacktestResult:
    """Pure-signal helper for callers that already have ``entries`` / ``exits``
    matrices (e.g. quick grid searches). Returns a :class:`BacktestResult`."""
    vbt = _import_vbt()
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        init_cash=init_cash,
        fees=fees,
        slippage=slippage,
        freq=freq,
    )
    return _to_backtest_result(pf, close, init_cash)


def ma_crossover_grid(
    close: pd.Series,
    fast_windows: list[int],
    slow_windows: list[int],
    init_cash: float = 100000.0,
    fees: float = 0.001,
) -> pd.DataFrame:
    """Run a 2D MA-crossover grid search and return the total-return heatmap.

    Mirrors the vectorbt README 'test 10,000 dual-SMA window combinations'
    pattern. Useful as a fast alpha screen before a full backtest.
    """
    vbt = _import_vbt()
    fast_ma = vbt.MA.run(close, window=fast_windows, short_name="fast")
    slow_ma = vbt.MA.run(close, window=slow_windows, short_name="slow")
    entries = fast_ma.ma_crossed_above(slow_ma)
    exits = fast_ma.ma_crossed_below(slow_ma)
    pf = vbt.Portfolio.from_signals(close, entries, exits, init_cash=init_cash, fees=fees)
    try:
        total = pf.total_return()
    except Exception:
        total = pd.Series(dtype=float)
    if isinstance(total, pd.Series):
        out = total.to_frame("total_return").reset_index()
    else:
        out = pd.DataFrame({"total_return": [float(total)]})
    return out


__all__ = [
    "VectorbtEngine",
    "run_vectorized_signals",
    "ma_crossover_grid",
]
