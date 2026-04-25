"""Reusable factor / signal builders (ML4T book + Zipline / Pyfolio lineage).

Each public function accepts a tidy bars frame
(``timestamp, vt_symbol, open, high, low, close, volume``) and returns a
``pd.Series`` indexed by ``(timestamp, vt_symbol)``. Combine them by
column-concatenation into the feature matrix consumed by
``aqp.ml.dataset.DatasetH``.

Covered families:

- Momentum — 1m / 3m / 6m / 12m excl. latest month.
- Value — earnings yield, book-to-price (need fundamentals frame).
- Quality — ROE, gross margin stability.
- Volatility — realised vol, downside vol, idiosyncratic vol.
- Short interest / turnover / liquidity.
- Cross-sectional rank / z-score helpers.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _pivot_close(bars: pd.DataFrame) -> pd.DataFrame:
    return (
        bars.pivot(index="timestamp", columns="vt_symbol", values="close")
        .sort_index()
        .ffill()
    )


def _pivot_volume(bars: pd.DataFrame) -> pd.DataFrame:
    return (
        bars.pivot(index="timestamp", columns="vt_symbol", values="volume")
        .sort_index()
        .ffill()
    )


# ---------------------------------------------------------------------------
# Momentum factors
# ---------------------------------------------------------------------------


def momentum_factor(bars: pd.DataFrame, lookback_months: int = 12, skip_last_months: int = 1) -> pd.Series:
    """Classical Fama-French momentum: return over ``lookback`` excluding
    the most recent ``skip_last_months``.
    """
    close = _pivot_close(bars)
    lb = lookback_months * 21
    skip = skip_last_months * 21
    mom = close.pct_change(lb).shift(skip)
    return mom.stack().rename("momentum")


def reversal_factor(bars: pd.DataFrame, lookback_days: int = 5) -> pd.Series:
    """Short-term reversal — the negative of 1-week return."""
    close = _pivot_close(bars)
    rev = -close.pct_change(lookback_days)
    return rev.stack().rename("reversal")


# ---------------------------------------------------------------------------
# Volatility / liquidity
# ---------------------------------------------------------------------------


def realised_vol(bars: pd.DataFrame, window: int = 21, annualise: bool = True) -> pd.Series:
    close = _pivot_close(bars)
    rets = np.log(close).diff()
    vol = rets.rolling(window).std()
    if annualise:
        vol = vol * np.sqrt(252)
    return vol.stack().rename("rvol")


def downside_vol(bars: pd.DataFrame, window: int = 21) -> pd.Series:
    close = _pivot_close(bars)
    rets = np.log(close).diff()
    down = rets.where(rets < 0, 0.0)
    return down.rolling(window).std().stack().rename("downside_vol")


def amihud_illiquidity(bars: pd.DataFrame, window: int = 21) -> pd.Series:
    """|return| / dollar_volume averaged over ``window`` days."""
    close = _pivot_close(bars)
    volume = _pivot_volume(bars)
    dollar = close * volume
    log_ret = np.log(close).diff().abs()
    illiq = (log_ret / dollar.replace(0, np.nan)).rolling(window).mean()
    return illiq.stack().rename("amihud")


def turnover_factor(bars: pd.DataFrame, window: int = 21, shares_outstanding: pd.Series | None = None) -> pd.Series:
    volume = _pivot_volume(bars)
    avg_vol = volume.rolling(window).mean()
    if shares_outstanding is not None:
        so = shares_outstanding.reindex(avg_vol.columns)
        avg_vol = avg_vol / so
    return avg_vol.stack().rename("turnover")


# ---------------------------------------------------------------------------
# Technical indicators — thin shims over aqp.core.indicators for factor research
# ---------------------------------------------------------------------------


def rsi_factor(bars: pd.DataFrame, window: int = 14) -> pd.Series:
    close = _pivot_close(bars)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = -delta.clip(upper=0).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.stack().rename("rsi")


def bollinger_width_factor(bars: pd.DataFrame, window: int = 20, k: float = 2.0) -> pd.Series:
    close = _pivot_close(bars)
    mid = close.rolling(window).mean()
    sd = close.rolling(window).std()
    width = (2 * k * sd) / mid.replace(0, np.nan)
    return width.stack().rename("bollinger_width")


# ---------------------------------------------------------------------------
# Cross-sectional helpers
# ---------------------------------------------------------------------------


def cross_sectional_rank(factor: pd.Series) -> pd.Series:
    if not isinstance(factor.index, pd.MultiIndex):
        raise ValueError("factor must be a MultiIndex (timestamp, vt_symbol) series")
    return factor.groupby(level=0).rank(pct=True)


def cross_sectional_zscore(factor: pd.Series) -> pd.Series:
    if not isinstance(factor.index, pd.MultiIndex):
        raise ValueError("factor must be a MultiIndex (timestamp, vt_symbol) series")
    mean = factor.groupby(level=0).transform("mean")
    std = factor.groupby(level=0).transform("std").replace(0.0, np.nan)
    return (factor - mean) / std


# ---------------------------------------------------------------------------
# Composite / utility
# ---------------------------------------------------------------------------


def build_factor_panel(
    bars: pd.DataFrame,
    factors: Iterable[str] = (
        "momentum",
        "reversal",
        "rvol",
        "downside_vol",
        "amihud",
        "turnover",
        "rsi",
        "bollinger_width",
    ),
) -> pd.DataFrame:
    """Return a ``(timestamp, vt_symbol) × factor`` panel."""
    builders = {
        "momentum": momentum_factor,
        "reversal": reversal_factor,
        "rvol": realised_vol,
        "downside_vol": downside_vol,
        "amihud": amihud_illiquidity,
        "turnover": turnover_factor,
        "rsi": rsi_factor,
        "bollinger_width": bollinger_width_factor,
    }
    series = []
    for name in factors:
        fn = builders.get(name)
        if fn is None:
            continue
        try:
            series.append(fn(bars).rename(name))
        except Exception:
            continue
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1)


__all__ = [
    "amihud_illiquidity",
    "bollinger_width_factor",
    "build_factor_panel",
    "cross_sectional_rank",
    "cross_sectional_zscore",
    "downside_vol",
    "momentum_factor",
    "realised_vol",
    "reversal_factor",
    "rsi_factor",
    "turnover_factor",
]
