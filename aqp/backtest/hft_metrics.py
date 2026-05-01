"""HFT-aware backtest metrics.

Ports ``py-hftbacktest/hftbacktest/stats/metrics.py`` to plain pandas /
numpy so they slot into AQP's existing ``BacktestResult.summary`` dict.

Sample-aware metrics correctly annualise Sharpe / Sortino when the bar
frequency differs from the assumed 252 trading days (e.g. crypto 5m
samples = 105120 samples per year).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _samples_per_year(returns: pd.Series, days_per_year: int = 365) -> float:
    """Infer samples-per-year from a returns series with a DatetimeIndex."""
    if not isinstance(returns.index, pd.DatetimeIndex) or len(returns) < 2:
        return float(252)
    spans = (returns.index[-1] - returns.index[0]).total_seconds()
    if spans <= 0:
        return float(252)
    samples_per_second = len(returns) / spans
    return float(samples_per_second * days_per_year * 86_400)


def sample_aware_sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    days_per_year: int = 365,
) -> float:
    """Annualised Sharpe ratio using the actual sample frequency.

    For crypto strategies use ``days_per_year=365``; for equity use 252.
    """
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    samples_per_year = _samples_per_year(r, days_per_year)
    excess = r - risk_free_rate / samples_per_year
    sigma = float(excess.std(ddof=1))
    if sigma <= 0:
        return float("nan")
    return float(excess.mean() / sigma * np.sqrt(samples_per_year))


def sample_aware_sortino(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    days_per_year: int = 365,
) -> float:
    """Annualised Sortino ratio using the actual sample frequency."""
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    samples_per_year = _samples_per_year(r, days_per_year)
    excess = r - risk_free_rate / samples_per_year
    downside = excess[excess < 0]
    if len(downside) == 0:
        return float("inf")
    sigma_d = float(downside.std(ddof=1))
    if sigma_d <= 0:
        return float("nan")
    return float(excess.mean() / sigma_d * np.sqrt(samples_per_year))


def max_position(positions: pd.Series) -> float:
    """Largest absolute position size at any point."""
    if positions.empty:
        return 0.0
    return float(positions.abs().max())


def mean_position_value(position_values: pd.Series) -> float:
    """Mean absolute position value (in account currency)."""
    if position_values.empty:
        return 0.0
    return float(position_values.abs().mean())


def median_position_value(position_values: pd.Series) -> float:
    if position_values.empty:
        return 0.0
    return float(position_values.abs().median())


def mean_leverage(position_values: pd.Series, equity: pd.Series) -> float:
    """Mean ratio ``|position_value| / equity``."""
    if position_values.empty or equity.empty:
        return 0.0
    aligned = pd.concat([position_values.rename("pos"), equity.rename("eq")], axis=1).dropna()
    if aligned.empty:
        return 0.0
    nonzero = aligned[aligned["eq"].abs() > 1e-9]
    if nonzero.empty:
        return 0.0
    return float((nonzero["pos"].abs() / nonzero["eq"].abs()).mean())


def max_leverage(position_values: pd.Series, equity: pd.Series) -> float:
    if position_values.empty or equity.empty:
        return 0.0
    aligned = pd.concat([position_values.rename("pos"), equity.rename("eq")], axis=1).dropna()
    nonzero = aligned[aligned["eq"].abs() > 1e-9]
    if nonzero.empty:
        return 0.0
    return float((nonzero["pos"].abs() / nonzero["eq"].abs()).max())


def return_over_trade(total_return: float, n_trades: int) -> float:
    """PnL per trade (not per round-trip)."""
    return float(total_return / max(n_trades, 1))


def fill_ratio(fills: int, orders: int) -> float:
    return float(fills / max(orders, 1))


def trading_volume(quantities: pd.Series) -> float:
    """Sum of |quantity| across all fills."""
    if quantities.empty:
        return 0.0
    return float(quantities.abs().sum())


def trading_value(prices: pd.Series, quantities: pd.Series) -> float:
    """Sum of |price * quantity| across all fills."""
    aligned = pd.concat([prices.rename("p"), quantities.rename("q")], axis=1).dropna()
    if aligned.empty:
        return 0.0
    return float((aligned["p"] * aligned["q"]).abs().sum())


def hft_summary(
    returns: pd.Series,
    positions: pd.Series,
    equity: pd.Series,
    fills: int = 0,
    orders: int = 0,
    *,
    days_per_year: int = 365,
) -> dict[str, float]:
    """Compute the full HFT-aware summary dict for ``BacktestResult.summary``.

    Returns a flat ``{metric: value}`` mapping suitable to merge into the
    existing summary fields.
    """
    position_values = positions * equity if not positions.empty and not equity.empty else pd.Series(dtype=float)
    return {
        "hft_sharpe_sample_aware": sample_aware_sharpe(returns, days_per_year=days_per_year),
        "hft_sortino_sample_aware": sample_aware_sortino(returns, days_per_year=days_per_year),
        "hft_max_position": max_position(positions),
        "hft_mean_position_value": mean_position_value(position_values),
        "hft_median_position_value": median_position_value(position_values),
        "hft_mean_leverage": mean_leverage(position_values, equity),
        "hft_max_leverage": max_leverage(position_values, equity),
        "hft_fill_ratio": fill_ratio(fills, orders),
        "hft_n_orders": float(orders),
        "hft_n_fills": float(fills),
    }


__all__ = [
    "fill_ratio",
    "hft_summary",
    "max_leverage",
    "max_position",
    "mean_leverage",
    "mean_position_value",
    "median_position_value",
    "return_over_trade",
    "sample_aware_sharpe",
    "sample_aware_sortino",
    "trading_value",
    "trading_volume",
]
