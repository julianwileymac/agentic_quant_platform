"""Convert a vbt-pro ``Portfolio`` to AQP :class:`BacktestResult`.

Centralised so every constructor mode (``signals``, ``orders``, ``optimizer``,
``holding``, ``random``) emits the same shape and the runner / persistence /
UI layers do not need to branch on engine.

Native vbt stats are preserved under ``vbt_*`` keys in ``summary`` so callers
can drill into Calmar / SQN / win_rate without re-computing.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.backtest.engine import BacktestResult
from aqp.backtest.metrics import summarise

logger = logging.getLogger(__name__)


def portfolio_to_backtest_result(
    pf: Any,
    close: pd.DataFrame,
    initial_cash: float,
    *,
    engine: str = "vectorbt-pro",
    mode: str = "signals",
    extra_summary: dict[str, Any] | None = None,
    signal_records: list[dict[str, Any]] | None = None,
) -> BacktestResult:
    """Translate ``vbt.Portfolio`` into :class:`BacktestResult`.

    Parameters
    ----------
    pf:
        A vbt-pro ``Portfolio`` instance.
    close:
        The close panel handed to the constructor (used to anchor the index
        when the portfolio is empty).
    initial_cash:
        Starting capital — used to normalise the equity curve so
        ``summarise()`` returns the conventional total-return interpretation.
    engine:
        Label written to ``summary["engine"]`` so callers can branch on it.
    mode:
        Sub-mode tag (``signals`` / ``orders`` / ``optimizer`` / ``holding`` /
        ``random``).
    extra_summary:
        Optional dict merged into ``summary`` after defaults.
    signal_records:
        Optional per-bar signal metadata to attach to ``result.signals``.
    """
    equity = _equity_curve(pf, initial_cash)
    trades = _trades_frame(pf)
    orders = _orders_frame(pf)

    summary = summarise(equity, trades if not trades.empty else None)
    summary["engine"] = engine
    summary["mode"] = mode
    summary.update(_native_stats(pf))
    if extra_summary:
        summary.update(extra_summary)

    first_ts = equity.index[0] if len(equity) else None
    last_ts = equity.index[-1] if len(equity) else None
    final_equity = float(equity.iloc[-1]) if len(equity) else float(initial_cash)

    signals_df = (
        pd.DataFrame(signal_records) if signal_records else pd.DataFrame()
    )

    return BacktestResult(
        equity_curve=equity,
        trades=trades,
        orders=orders,
        signals=signals_df,
        tickets=[],
        summary=summary,
        start=first_ts.to_pydatetime() if first_ts is not None else None,
        end=last_ts.to_pydatetime() if last_ts is not None else None,
        initial_cash=float(initial_cash),
        final_equity=final_equity,
    )


def _equity_curve(pf: Any, initial_cash: float) -> pd.Series:
    try:
        value = pf.value()
    except Exception:
        try:
            value = pf.total_value()
        except Exception:
            value = pd.Series(dtype=float)

    if isinstance(value, pd.DataFrame):
        equity = value.sum(axis=1)
    else:
        equity = value
    if equity is None or len(equity) == 0:
        return pd.Series(dtype=float, name="equity")
    equity = equity.astype(float).sort_index()
    equity.name = "equity"

    if len(equity):
        first = float(equity.iloc[0])
        if first == 0.0:
            equity = equity + initial_cash
        elif abs(first - initial_cash) > 1e-6:
            equity = equity / first * initial_cash
    return equity


def _trades_frame(pf: Any) -> pd.DataFrame:
    try:
        trades = pf.trades.records_readable.copy()
    except Exception:
        return pd.DataFrame()
    if trades.empty:
        return trades
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
        "Avg Entry Price": "avg_entry_price",
        "Avg Exit Price": "avg_exit_price",
        "Status": "status",
    }
    trades = trades.rename(columns={k: v for k, v in col_map.items() if k in trades.columns})
    if "side" in trades.columns:
        trades["side"] = trades["side"].astype(str).str.lower().map(
            lambda s: "buy" if "long" in s else ("sell" if "short" in s else s)
        )
    for missing in ("slippage", "strategy_id"):
        if missing not in trades.columns:
            trades[missing] = 0.0 if missing == "slippage" else ""
    return trades


def _orders_frame(pf: Any) -> pd.DataFrame:
    try:
        orders = pf.orders.records_readable.copy()
    except Exception:
        return pd.DataFrame()
    if orders.empty:
        return orders
    orders = orders.rename(
        columns={
            "Order Id": "order_id",
            "Column": "vt_symbol",
            "Timestamp": "created_at",
            "Side": "side",
            "Size": "quantity",
            "Price": "price",
            "Fees": "fees",
            "Index": "bar_idx",
        }
    )
    if "side" in orders.columns:
        orders["side"] = orders["side"].astype(str).str.lower()
    orders["status"] = "filled"
    return orders


def _native_stats(pf: Any) -> dict[str, Any]:
    """Extract library-native stats with a stable ``vbt_`` prefix."""
    try:
        native = pf.stats()
    except Exception:
        return {}
    if hasattr(native, "to_dict"):
        native = native.to_dict()
    if not isinstance(native, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in native.items():
        norm_key = (
            str(key)
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("[%]", "pct")
            .replace("(%)", "pct")
        )
        try:
            out[f"vbt_{norm_key}"] = float(value)
        except (TypeError, ValueError):
            out[f"vbt_{norm_key}"] = value
    return out


__all__ = ["portfolio_to_backtest_result"]
