"""Technical-indicator feature engineer (FinRL-style).

Adds indicators to a tidy long-format bars frame keyed by ``vt_symbol``.
Pure pandas/numpy implementation — no external technical-analysis
dependencies so the package stays lean and Python-version agnostic.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

import numpy as np
import pandas as pd

from aqp.core.registry import register

logger = logging.getLogger(__name__)

_DEFAULT_INDICATORS = (
    "sma_20",
    "sma_50",
    "ema_12",
    "ema_26",
    "macd",
    "rsi_14",
    "bbands_upper",
    "bbands_lower",
    "atr_14",
    "turbulence",
)


@register("FeatureEngineer")
class FeatureEngineer:
    """Adds a curated set of indicators to a bars frame.

    ``indicators`` controls the built-in pure-pandas pipeline below.
    ``extra_indicators`` is delegated to :class:`aqp.data.indicators_zoo.IndicatorZoo`
    after the built-ins run, so callers can mix in the full Lean-style
    indicator suite — including ``ModelPred:deployment_id=...`` model
    predictions — without re-implementing the panel join here.
    """

    def __init__(
        self,
        indicators: Iterable[str] = _DEFAULT_INDICATORS,
        extra_indicators: Iterable[str] | None = None,
    ) -> None:
        self.indicators = list(indicators)
        self.extra_indicators = list(extra_indicators) if extra_indicators else []

    def transform(self, bars: pd.DataFrame) -> pd.DataFrame:
        if bars.empty:
            return bars
        frames: list[pd.DataFrame] = []
        for _vt_symbol, sub in bars.sort_values("timestamp").groupby("vt_symbol", sort=False):
            sub = sub.copy()
            close = sub["close"]
            high = sub["high"]
            low = sub["low"]

            if "sma_20" in self.indicators:
                sub["sma_20"] = close.rolling(20).mean()
            if "sma_50" in self.indicators:
                sub["sma_50"] = close.rolling(50).mean()
            if "ema_12" in self.indicators:
                sub["ema_12"] = close.ewm(span=12, adjust=False).mean()
            if "ema_26" in self.indicators:
                sub["ema_26"] = close.ewm(span=26, adjust=False).mean()
            if "macd" in self.indicators:
                ema12 = close.ewm(span=12, adjust=False).mean()
                ema26 = close.ewm(span=26, adjust=False).mean()
                sub["macd"] = ema12 - ema26
                sub["macd_signal"] = sub["macd"].ewm(span=9, adjust=False).mean()
            if "rsi_14" in self.indicators:
                sub["rsi_14"] = _rsi(close, 14)
            if "bbands_upper" in self.indicators or "bbands_lower" in self.indicators:
                sma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                sub["bbands_upper"] = sma20 + 2 * std20
                sub["bbands_lower"] = sma20 - 2 * std20
                sub["bbands_mid"] = sma20
            if "atr_14" in self.indicators:
                tr = pd.concat(
                    [
                        (high - low).abs(),
                        (high - close.shift()).abs(),
                        (low - close.shift()).abs(),
                    ],
                    axis=1,
                ).max(axis=1)
                sub["atr_14"] = tr.rolling(14).mean()
            if "cci_30" in self.indicators:
                tp = (high + low + close) / 3
                tp_mean = tp.rolling(30).mean()
                tp_std = tp.rolling(30).std()
                sub["cci_30"] = (tp - tp_mean) / (0.015 * tp_std.replace(0, np.nan))
            if "dx_30" in self.indicators:
                sub["dx_30"] = _dx(high, low, close, 30)
            if "turbulence" in self.indicators:
                returns = close.pct_change().fillna(0)
                sub["turbulence"] = (returns**2).rolling(252).mean() ** 0.5 * 1000
            frames.append(sub)
        out = pd.concat(frames, ignore_index=True)
        if self.extra_indicators:
            try:
                from aqp.data.indicators_zoo import IndicatorZoo

                out = IndicatorZoo().transform(out, indicators=self.extra_indicators)
            except Exception:
                logger.exception("FeatureEngineer extra_indicators failed")
        return out

    fit_transform = transform


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _dx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    up = high.diff()
    dn = -low.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat(
        [(high - low).abs(), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1
    ).max(axis=1)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))
    return 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
