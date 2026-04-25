"""Vectorised backtester for rapid hypothesis screening.

Trades off execution fidelity for speed — useful when the Hypothesis
Designer wants to rank many candidate alphas before sending the winner
through the event-driven engine.
"""
from __future__ import annotations

import pandas as pd

from aqp.backtest.metrics import summarise


def vector_backtest(
    bars: pd.DataFrame,
    signal_column: str = "signal",
    price_column: str = "close",
    initial_cash: float = 100000.0,
    commission_pct: float = 0.0005,
) -> dict:
    """Portfolio-of-signals vectorised backtest.

    ``bars`` must contain columns ``timestamp, vt_symbol, <price_column>, <signal_column>``
    where ``signal_column`` is in ``[-1, 1]``. Pivot + shift(1) + forward-fill applied.
    """
    required = {"timestamp", "vt_symbol", price_column, signal_column}
    missing = required - set(bars.columns)
    if missing:
        raise KeyError(f"Missing columns: {missing}")

    df = bars.copy().sort_values(["timestamp", "vt_symbol"])
    prices = df.pivot(index="timestamp", columns="vt_symbol", values=price_column).ffill()
    signals = (
        df.pivot(index="timestamp", columns="vt_symbol", values=signal_column)
        .reindex(prices.index)
        .fillna(0)
    )
    signals = signals.shift(1).fillna(0).clip(-1, 1)
    # equal-weight per-bar signal → normalised weights
    gross = signals.abs().sum(axis=1).replace(0, 1)
    weights = signals.div(gross, axis=0)

    returns = prices.pct_change().fillna(0)
    portfolio_returns = (weights * returns).sum(axis=1)

    turnover = weights.diff().abs().sum(axis=1).fillna(0)
    cost = turnover * commission_pct
    portfolio_returns = portfolio_returns - cost

    equity = (1 + portfolio_returns).cumprod() * initial_cash

    summary = summarise(equity)
    summary["turnover"] = float(turnover.sum())
    return {
        "equity_curve": equity,
        "returns": portfolio_returns,
        "weights": weights,
        "summary": summary,
    }
