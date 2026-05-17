"""Regime / state classification helpers.

Pulled from QTradeX (``ma_sabres``, ``blackhole``, ``mac_dr_si``) and
common ADX trend/range gating idioms.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class Regime(str, Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"
    COMPRESSED = "compressed"
    SURGE = "surge"
    # VIX-percentile bucketing (AgentQuant-inspired)
    CRISIS = "crisis"
    HIGH_VOL = "high_vol"
    MID_VOL = "mid_vol"
    LOW_VOL = "low_vol"


@dataclass
class RegimeReading:
    regime: Regime
    score: float
    extras: dict[str, float]


# ---------------------------------------------------------------------------
# ADX-gated trend vs range classifier (from BBadXMacDrSi)
# ---------------------------------------------------------------------------


class ADXRegimeClassifier:
    """Classify each bar as trending vs ranging using ADX threshold.

    ``adx > threshold`` => :data:`Regime.TRENDING`; otherwise
    :data:`Regime.RANGING`. ``threshold`` defaults to 25, the
    industry-standard "directional" cutoff.
    """

    def __init__(self, threshold: float = 25.0) -> None:
        self.threshold = float(threshold)

    def classify(self, adx: pd.Series) -> pd.Series:
        return np.where(adx > self.threshold, Regime.TRENDING.value, Regime.RANGING.value)

    def latest(self, adx_value: float) -> RegimeReading:
        regime = Regime.TRENDING if adx_value > self.threshold else Regime.RANGING
        return RegimeReading(
            regime=regime,
            score=float(adx_value - self.threshold),
            extras={"adx": float(adx_value), "threshold": self.threshold},
        )


# ---------------------------------------------------------------------------
# Multi-MA slope vote (from QTradeX ma_sabres)
# ---------------------------------------------------------------------------

MaKind = Literal["sma", "ema", "wma", "hma", "kama"]


def _moving_average(series: pd.Series, window: int, kind: MaKind = "sma") -> pd.Series:
    if kind == "sma":
        return series.rolling(window).mean()
    if kind == "ema":
        return series.ewm(span=window, adjust=False).mean()
    if kind == "wma":
        weights = np.arange(1, window + 1, dtype=float)
        weights /= weights.sum()
        return series.rolling(window).apply(lambda w: float(np.dot(w, weights)), raw=True)
    if kind == "hma":
        wma_half = _moving_average(series, max(window // 2, 1), "wma")
        wma_full = _moving_average(series, window, "wma")
        diff = 2 * wma_half - wma_full
        return _moving_average(diff, max(int(np.sqrt(window)), 1), "wma")
    if kind == "kama":
        change = (series.diff(window).abs())
        volatility = series.diff().abs().rolling(window).sum()
        er = change / volatility.replace(0, np.nan)
        fast_sc = 2.0 / (2 + 1)
        slow_sc = 2.0 / (30 + 1)
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        kama = series.copy().astype(float)
        kama.iloc[:window] = series.iloc[:window].mean()
        for i in range(window, len(series)):
            kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (series.iloc[i] - kama.iloc[i - 1])
        return kama
    raise ValueError(f"unknown ma kind: {kind}")


class MultiMASlopeVote:
    """Cast a buy/sell vote per MA based on slope sign (:class:`np.diff`).

    Result is the net consensus across MAs: ``+N`` to ``-N`` where ``N`` is
    the number of MAs configured.
    """

    def __init__(
        self,
        windows: tuple[int, ...] = (5, 10, 20, 50, 100),
        kinds: tuple[MaKind, ...] = ("sma", "ema", "wma", "hma", "kama"),
    ) -> None:
        if len(windows) != len(kinds):
            raise ValueError("windows and kinds must be the same length")
        self.windows = windows
        self.kinds = kinds

    def vote(self, close: pd.Series) -> pd.Series:
        votes = pd.Series(0.0, index=close.index, name="ma_vote")
        for w, k in zip(self.windows, self.kinds, strict=False):
            ma = _moving_average(close, w, k)
            slope = ma.diff()
            votes = votes + np.sign(slope).fillna(0)
        return votes

    def latest(self, close: pd.Series) -> RegimeReading:
        v = self.vote(close)
        if len(v) == 0 or pd.isna(v.iloc[-1]):
            return RegimeReading(regime=Regime.NEUTRAL, score=0.0, extras={})
        score = float(v.iloc[-1])
        n = len(self.windows)
        if score >= n * 0.6:
            regime = Regime.BULL
        elif score <= -n * 0.6:
            regime = Regime.BEAR
        else:
            regime = Regime.NEUTRAL
        return RegimeReading(regime=regime, score=score, extras={"n_mas": float(n)})


# ---------------------------------------------------------------------------
# Black-hole compression / surge (from QTradeX blackhole)
# ---------------------------------------------------------------------------


class BlackHoleZone:
    """Classify volatility regimes as compressed / normal / surge.

    Compressed zones (low ATR vs trailing average) often precede
    breakouts; surge zones are sustained volatility expansions.
    """

    def __init__(
        self,
        atr_window: int = 14,
        avg_window: int = 100,
        compression_ratio: float = 0.6,
        surge_ratio: float = 1.6,
    ) -> None:
        self.atr_window = atr_window
        self.avg_window = avg_window
        self.compression_ratio = compression_ratio
        self.surge_ratio = surge_ratio

    def _atr(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.rolling(self.atr_window).mean()

    def classify(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        atr = self._atr(high, low, close)
        avg = atr.rolling(self.avg_window).mean()
        ratio = atr / avg
        out = np.where(
            ratio < self.compression_ratio,
            Regime.COMPRESSED.value,
            np.where(ratio > self.surge_ratio, Regime.SURGE.value, Regime.NEUTRAL.value),
        )
        return pd.Series(out, index=close.index, name="blackhole_regime")


# ---------------------------------------------------------------------------
# VIX-percentile classifier (AgentQuant inspired)
# ---------------------------------------------------------------------------


class VIXPercentileRegimeClassifier:
    """Classify a volatility series into Crisis / HighVol / MidVol / LowVol.

    AgentQuant's strategy memory keys regime by VIX percentile over a
    rolling 252-day window. Strategies that succeeded under each
    regime get re-applied when the same regime is detected later,
    avoiding a cold-start hypothesis loop.

    The classifier is deliberately series-agnostic — pass any
    volatility-like series (the literal ``^VIX`` close, realised vol,
    or a custom regime indicator) and the percentile bucketing kicks
    in. The default thresholds ``crisis=0.95 / high=0.75 / mid=0.50``
    follow the published AgentQuant defaults.
    """

    def __init__(
        self,
        *,
        window: int = 252,
        crisis_pct: float = 0.95,
        high_pct: float = 0.75,
        mid_pct: float = 0.50,
    ) -> None:
        if not 0.0 < mid_pct < high_pct < crisis_pct < 1.0:
            raise ValueError(
                "thresholds must satisfy 0 < mid < high < crisis < 1; "
                f"got mid={mid_pct} high={high_pct} crisis={crisis_pct}"
            )
        self.window = int(window)
        self.crisis_pct = float(crisis_pct)
        self.high_pct = float(high_pct)
        self.mid_pct = float(mid_pct)

    def classify(self, vol_series: pd.Series) -> pd.Series:
        """Return a per-bar :class:`Regime` label series.

        Bars before ``window`` observations are :data:`Regime.NEUTRAL`
        because the percentile is not yet meaningful.
        """
        if vol_series is None or len(vol_series) == 0:
            return pd.Series(dtype=str, name="vix_regime")
        rolled = vol_series.rolling(self.window, min_periods=max(30, self.window // 4))

        def _bucket(window: pd.Series) -> str:
            if window.empty or pd.isna(window.iloc[-1]):
                return Regime.NEUTRAL.value
            if len(window.dropna()) < 30:
                return Regime.NEUTRAL.value
            value = float(window.iloc[-1])
            ranks = window.dropna().rank(pct=True)
            if ranks.empty:
                return Regime.NEUTRAL.value
            pct = float(ranks.iloc[-1])
            if pct >= self.crisis_pct:
                return Regime.CRISIS.value
            if pct >= self.high_pct:
                return Regime.HIGH_VOL.value
            if pct >= self.mid_pct:
                return Regime.MID_VOL.value
            return Regime.LOW_VOL.value

        return rolled.apply(_bucket, raw=False)

    def latest(self, vol_series: pd.Series) -> RegimeReading:
        """Return the regime + percentile for the most recent observation."""
        if vol_series is None or len(vol_series) == 0:
            return RegimeReading(regime=Regime.NEUTRAL, score=0.0, extras={})
        clean = vol_series.dropna()
        if len(clean) < 30:
            return RegimeReading(regime=Regime.NEUTRAL, score=0.0, extras={"n": float(len(clean))})
        window = clean.tail(self.window)
        if window.empty:
            return RegimeReading(regime=Regime.NEUTRAL, score=0.0, extras={})
        ranks = window.rank(pct=True)
        if ranks.empty:
            return RegimeReading(regime=Regime.NEUTRAL, score=0.0, extras={})
        pct = float(ranks.iloc[-1])
        if pct >= self.crisis_pct:
            regime = Regime.CRISIS
        elif pct >= self.high_pct:
            regime = Regime.HIGH_VOL
        elif pct >= self.mid_pct:
            regime = Regime.MID_VOL
        else:
            regime = Regime.LOW_VOL
        return RegimeReading(
            regime=regime,
            score=pct,
            extras={
                "value": float(window.iloc[-1]),
                "window_min": float(window.min()),
                "window_max": float(window.max()),
                "window_size": float(len(window)),
                "crisis_pct": self.crisis_pct,
                "high_pct": self.high_pct,
                "mid_pct": self.mid_pct,
            },
        )


__all__ = [
    "ADXRegimeClassifier",
    "BlackHoleZone",
    "MultiMASlopeVote",
    "Regime",
    "RegimeReading",
    "VIXPercentileRegimeClassifier",
]
