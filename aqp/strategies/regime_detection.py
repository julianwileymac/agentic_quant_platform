"""Market regime detection helpers.

Inspired by `FinRL-X
<https://github.com/AI4Finance-Foundation/FinRL-Trading>`_'s
``adaptive_rotation/market_regime.py`` — distilled to the canonical
"slow gate / fast overlay" recipe so any alpha can ask:

    >>> from aqp.strategies.regime_detection import slow_regime_state
    >>> state = slow_regime_state(spx_close, vix_close)
    >>> if state == "risk_on": ...

The slow regime is a weekly structural gate; the fast overlay is a daily
emergency switch. Both consume only price + VIX so they work with the
default Parquet lake without extra adapters.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RegimeState = Literal["risk_on", "neutral", "risk_off"]


@dataclass
class SlowRegimeReport:
    state: RegimeState
    risk_score: int
    spx_below_ma_26w: bool
    drawdown_stress: bool
    volatility_stress: bool
    spx_drawdown_13w: float
    vix_z_score: float


@dataclass
class FastOverlayReport:
    active: bool
    price_shock: bool
    volatility_shock: bool
    spx_drop_pct: float
    vix_change: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_daily(close: pd.Series) -> pd.Series:
    s = pd.Series(close).copy()
    s.index = pd.to_datetime(s.index)
    return s.sort_index().asfreq("B").ffill()


def _robust_zscore(x: pd.Series, window: int = 252) -> float:
    """Median + MAD-based z-score for the latest value of ``x``.

    Falls back to a regular z-score if MAD is zero.
    """
    tail = x.tail(window).dropna()
    if len(tail) < 30:
        return 0.0
    median = float(tail.median())
    mad = float(np.median(np.abs(tail - median)))
    if mad < 1e-9:
        std = float(tail.std() or 1.0)
        return float((tail.iloc[-1] - tail.mean()) / std)
    # 1.4826 scales MAD to sigma for normal data.
    return float((tail.iloc[-1] - median) / (1.4826 * mad))


# ---------------------------------------------------------------------------
# Slow regime gate (weekly horizon, structural)
# ---------------------------------------------------------------------------


def slow_regime(
    spx_close: pd.Series,
    vix_close: pd.Series,
    *,
    ma_weeks: int = 26,
    drawdown_lookback_weeks: int = 13,
    vix_zscore_window: int = 252,
    drawdown_threshold: float = 0.10,
    vix_zscore_threshold: float = 2.0,
) -> SlowRegimeReport:
    """Three-state slow regime gate driven by SPX trend + VIX stress.

    Risk score is the number of bearish components active:

    - ``trend_deterioration``: SPX < its 26-week MA
    - ``drawdown_stress``: 13-week rolling drawdown deeper than ``drawdown_threshold``
    - ``volatility_stress``: VIX z-score exceeds ``vix_zscore_threshold``

    Score 0 → ``risk_on``, 1 → ``neutral``, ≥2 → ``risk_off``.
    """
    spx = _ensure_daily(spx_close)
    vix = _ensure_daily(vix_close)

    if spx.empty or vix.empty:
        return SlowRegimeReport(
            state="neutral",
            risk_score=0,
            spx_below_ma_26w=False,
            drawdown_stress=False,
            volatility_stress=False,
            spx_drawdown_13w=0.0,
            vix_z_score=0.0,
        )

    ma_window = max(2, int(ma_weeks * 5))
    dd_window = max(2, int(drawdown_lookback_weeks * 5))

    ma = spx.rolling(window=ma_window, min_periods=ma_window // 2).mean()
    spx_below_ma = bool(spx.iloc[-1] < ma.iloc[-1]) if not ma.empty else False

    rolling_max = spx.rolling(window=dd_window, min_periods=dd_window // 2).max()
    drawdown = (spx / rolling_max - 1.0).fillna(0.0)
    spx_dd = float(drawdown.iloc[-1])
    drawdown_stress = spx_dd <= -float(drawdown_threshold)

    vix_z = _robust_zscore(vix, window=vix_zscore_window)
    volatility_stress = bool(vix_z >= vix_zscore_threshold)

    risk_score = int(spx_below_ma) + int(drawdown_stress) + int(volatility_stress)
    if risk_score == 0:
        state: RegimeState = "risk_on"
    elif risk_score == 1:
        state = "neutral"
    else:
        state = "risk_off"

    return SlowRegimeReport(
        state=state,
        risk_score=risk_score,
        spx_below_ma_26w=bool(spx_below_ma),
        drawdown_stress=bool(drawdown_stress),
        volatility_stress=bool(volatility_stress),
        spx_drawdown_13w=spx_dd,
        vix_z_score=float(vix_z),
    )


# ---------------------------------------------------------------------------
# Fast overlay (daily emergency switch)
# ---------------------------------------------------------------------------


def fast_overlay(
    spx_close: pd.Series,
    vix_close: pd.Series,
    *,
    price_shock_pct: float = 0.025,
    vix_jump: float = 5.0,
) -> FastOverlayReport:
    """Daily risk-off overlay driven by sudden moves in SPX / VIX.

    Returns ``active=True`` when **either** the latest SPX session drops
    by more than ``price_shock_pct`` or VIX rises by more than ``vix_jump``
    points since the previous session.
    """
    spx = _ensure_daily(spx_close)
    vix = _ensure_daily(vix_close)
    if len(spx) < 2 or len(vix) < 2:
        return FastOverlayReport(False, False, False, 0.0, 0.0)
    spx_drop = float(spx.iloc[-1] / spx.iloc[-2] - 1.0)
    vix_change = float(vix.iloc[-1] - vix.iloc[-2])
    price_shock = spx_drop <= -float(price_shock_pct)
    vol_shock = vix_change >= float(vix_jump)
    return FastOverlayReport(
        active=bool(price_shock or vol_shock),
        price_shock=bool(price_shock),
        volatility_shock=bool(vol_shock),
        spx_drop_pct=spx_drop,
        vix_change=vix_change,
    )


def slow_regime_state(spx_close: pd.Series, vix_close: pd.Series) -> RegimeState:
    """Convenience wrapper returning just the regime label."""
    return slow_regime(spx_close, vix_close).state


__all__ = [
    "FastOverlayReport",
    "RegimeState",
    "SlowRegimeReport",
    "fast_overlay",
    "slow_regime",
    "slow_regime_state",
]
