"""analyzingalpha-master strategy ports."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.data.cointegration import engle_granger
from aqp.strategies.qtradex.alphas import BasicAlphaBase, _ema, _rsi, _sma

logger = logging.getLogger(__name__)


@register("SectorMomentumAlpha", source="analyzingalpha", category="rotation")
class SectorMomentumAlpha(BasicAlphaBase):
    """Cross-sectional momentum on sector ETFs."""

    name = "SectorMomentumAlpha"

    def __init__(self, lookback: int = 63) -> None:
        self.lookback = lookback
        self.min_history = lookback

    def signal_for_symbol(self, sub, context):
        ret = sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback] - 1.0
        sign = 1 if ret > 0 else -1
        return sign, min(1.0, abs(ret) * 5), f"{self.lookback}-day ret={ret:.4f}"


@register("SectorRSIAlpha", source="analyzingalpha", category="oscillator")
class SectorRSIAlpha(BasicAlphaBase):
    """RSI(14) cross above 30 → buy, cross below 70 → sell on sector ETFs."""

    name = "SectorRSIAlpha"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.min_history = period * 3

    def signal_for_symbol(self, sub, context):
        rsi = _rsi(sub["close"], self.period)
        last = rsi.iloc[-1]
        prev = rsi.iloc[-2]
        if pd.isna(last) or pd.isna(prev):
            return None
        if last > self.oversold and prev <= self.oversold:
            return 1, 0.6, f"RSI cross up from {prev:.1f}"
        if last < self.overbought and prev >= self.overbought:
            return -1, 0.6, f"RSI cross down from {prev:.1f}"
        return None


@register("EquitiesStopLossStrategy", source="analyzingalpha", category="risk")
class EquitiesStopLossStrategy(BasicAlphaBase):
    """Trailing-stop strategy — sells when price drops X% from rolling high."""

    name = "EquitiesStopLossStrategy"

    def __init__(self, trail_pct: float = 0.10, lookback: int = 60) -> None:
        self.trail_pct = trail_pct
        self.lookback = lookback
        self.min_history = lookback

    def signal_for_symbol(self, sub, context):
        rolling_high = sub["close"].rolling(self.lookback).max().iloc[-1]
        last = sub["close"].iloc[-1]
        if pd.isna(rolling_high):
            return None
        drop = (last - rolling_high) / rolling_high
        if drop <= -self.trail_pct:
            return -1, 0.7, f"trail stop drop={drop:.3f}"
        return 1, 0.4, f"holding near high={rolling_high:.2f}"


@register("EquitiesBracketStrategy", source="analyzingalpha", category="risk")
class EquitiesBracketStrategy(BasicAlphaBase):
    """Bracket-order R:R-driven entry — long when 5-day return positive."""

    name = "EquitiesBracketStrategy"

    def __init__(self, risk_reward: float = 2.0, lookback: int = 5) -> None:
        self.risk_reward = risk_reward
        self.lookback = lookback
        self.min_history = lookback

    def signal_for_symbol(self, sub, context):
        ret = sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback] - 1.0
        if ret > 0:
            return 1, min(1.0, ret * 10), f"bracket entry ret={ret:.4f}"
        return None


@register("CryptoPriceShearMRAlpha", source="analyzingalpha", category="mean_reversion")
class CryptoPriceShearMRAlpha(BasicAlphaBase):
    """'Shear' = price - rolling regression line; mean-revert extremes."""

    name = "CryptoPriceShearMRAlpha"

    def __init__(self, lookback: int = 60, z_threshold: float = 2.0) -> None:
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.min_history = lookback

    def signal_for_symbol(self, sub, context):
        close = sub["close"].tail(self.lookback)
        if len(close) < self.lookback:
            return None
        x = np.arange(len(close))
        slope, intercept = np.polyfit(x, close.to_numpy(), 1)
        line = slope * x + intercept
        residuals = close.to_numpy() - line
        std = float(np.std(residuals))
        if std <= 0:
            return None
        z = float((close.iloc[-1] - line[-1]) / std)
        if z > self.z_threshold:
            return -1, min(1.0, abs(z) / 3), f"shear z={z:.2f} (overshoot)"
        if z < -self.z_threshold:
            return 1, min(1.0, abs(z) / 3), f"shear z={z:.2f} (undershoot)"
        return None


@register("StatArbPairsStrategy", source="analyzingalpha", category="stat_arb")
class StatArbPairsStrategy(BasicAlphaBase):
    """Engle-Granger cointegration pairs trade.

    Pair specification provided via ``context["pair"]`` =
    ``{"a": "AAPL.NASDAQ", "b": "MSFT.NASDAQ", "z_threshold": 2.0}``.
    """

    name = "StatArbPairsStrategy"

    def __init__(self, lookback: int = 252, z_threshold: float = 2.0) -> None:
        self.lookback = lookback
        self.z_threshold = z_threshold
        self.min_history = lookback

    def generate_signals(self, bars, universe, context):
        pair = context.get("pair")
        if not pair:
            return []
        a_vt, b_vt = pair["a"], pair["b"]
        a = bars[bars["vt_symbol"] == a_vt].sort_values("timestamp").set_index("timestamp")["close"]
        b = bars[bars["vt_symbol"] == b_vt].sort_values("timestamp").set_index("timestamp")["close"]
        if len(a) < self.lookback or len(b) < self.lookback:
            return []
        try:
            res = engle_granger(a.tail(self.lookback), b.tail(self.lookback), z_window=60)
        except (ValueError, ImportError):
            return []
        last_z = res.spread_z.iloc[-1] if not res.spread_z.empty else float("nan")
        if pd.isna(last_z) or abs(last_z) < self.z_threshold:
            return []
        from aqp.core.types import Direction, Signal, Symbol
        sign = -1 if last_z > 0 else 1
        return [
            Signal(
                symbol=Symbol.parse(a_vt),
                strength=min(1.0, abs(last_z) / 3),
                direction=Direction.LONG if sign > 0 else Direction.SHORT,
                source=self.name,
                rationale=f"pair z={last_z:.2f} hedge={res.hedge_ratio:.3f}",
            ),
            Signal(
                symbol=Symbol.parse(b_vt),
                strength=min(1.0, abs(last_z) / 3),
                direction=Direction.SHORT if sign > 0 else Direction.LONG,
                source=self.name,
                rationale=f"pair z={last_z:.2f} hedge={res.hedge_ratio:.3f}",
            ),
        ]


@register("UnemploymentMacroOverlayStrategy", source="analyzingalpha", category="macro")
class UnemploymentMacroOverlayStrategy(BasicAlphaBase):
    """Long equities only when unemployment trend is improving.

    FRED unemployment series passed via ``context["macro"]["unemployment"]``
    (a pd.Series).
    """

    name = "UnemploymentMacroOverlayStrategy"

    def __init__(self, sma_period: int = 12) -> None:
        self.sma_period = sma_period
        self.min_history = 1

    def generate_signals(self, bars, universe, context):
        macro = context.get("macro", {})
        unemp = macro.get("unemployment")
        if unemp is None or len(unemp) < self.sma_period:
            return []
        sma = unemp.rolling(self.sma_period).mean()
        if pd.isna(sma.iloc[-1]):
            return []
        improving = unemp.iloc[-1] < sma.iloc[-1]
        if not improving:
            return []
        from aqp.core.types import Direction, Signal
        return [
            Signal(symbol=s, strength=0.5, direction=Direction.LONG, source=self.name, rationale="unemployment improving")
            for s in universe
        ]


@register("ConnorsRSIAlpha", source="analyzingalpha", category="oscillator")
class ConnorsRSIAlpha(BasicAlphaBase):
    """Connors RSI = 1/3 RSI + 1/3 RSI(streak) + 1/3 PercentRank(roc)."""

    name = "ConnorsRSIAlpha"

    def __init__(self, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> None:
        self.rsi_period = rsi_period
        self.streak_period = streak_period
        self.rank_period = rank_period
        self.min_history = rank_period + 5

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        rsi_part = _rsi(close, self.rsi_period).iloc[-1]
        # streak = consecutive positive (or negative) days
        delta = close.diff()
        streak = 0
        for d in reversed(delta.tail(20).dropna().to_list()):
            if d > 0 and streak >= 0:
                streak += 1
            elif d < 0 and streak <= 0:
                streak -= 1
            else:
                break
        rsi_streak = _rsi(pd.Series([streak]).repeat(self.streak_period), self.streak_period).iloc[-1]
        roc = close.pct_change(1)
        rank_part = roc.tail(self.rank_period).rank(pct=True).iloc[-1] * 100
        if any(pd.isna(x) for x in (rsi_part, rsi_streak, rank_part)):
            return None
        crsi = (rsi_part + rsi_streak + rank_part) / 3.0
        if crsi < 10:
            return 1, 0.7, f"CRSI={crsi:.1f}<10 (oversold)"
        if crsi > 90:
            return -1, 0.7, f"CRSI={crsi:.1f}>90 (overbought)"
        return None
