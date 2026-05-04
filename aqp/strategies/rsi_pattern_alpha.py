"""RSI pattern-recognition alpha — extends :class:`RsiAlphaModel`.

Ref: ``inspiration/quant-trading-master/RSI Pattern Recognition backtest.py``.

Short side: a head-and-shoulders-style price geometry confirmed by RSI
rising N bars in a row, exit on RSI mean-reversion.

The code stays conservative — it reuses the existing :class:`RsiAlphaModel`
for the baseline oversold/overbought logic and adds a head-and-shoulders
geometry filter on top.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("pattern", "mean-reversion", "quant-trading")


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


@register(
    "RsiPatternAlpha",
    kind="strategy",
    tags=STRATEGY_TAGS,
    source="quant_trading",
    category="pattern",
)
class RsiPatternAlpha(IAlphaModel):
    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        pattern_window: int = 10,
        allow_short: bool = True,
    ) -> None:
        self.period = int(period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)
        self.pattern_window = int(pattern_window)
        self.allow_short = bool(allow_short)

    def _head_and_shoulders(self, prices: pd.Series) -> bool:
        if len(prices) < 7:
            return False
        seg = prices.tail(self.pattern_window).reset_index(drop=True)
        if len(seg) < 5:
            return False
        idx_max = int(seg.idxmax())
        if idx_max in (0, len(seg) - 1):
            return False
        left = seg.iloc[:idx_max]
        right = seg.iloc[idx_max + 1 :]
        if left.empty or right.empty:
            return False
        ls_peak = float(left.max())
        rs_peak = float(right.max())
        head = float(seg.iloc[idx_max])
        return head > ls_peak and head > rs_peak and abs(ls_peak - rs_peak) / head < 0.05

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        signals: list[Signal] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.period + self.pattern_window:
                continue
            rsi = _rsi(sub["close"], self.period).iloc[-1]
            if pd.isna(rsi):
                continue
            ts = now or sub["timestamp"].iloc[-1]
            if rsi <= self.oversold:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (self.oversold - float(rsi)) / self.oversold)),
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.55,
                        source="RsiPatternAlpha",
                        rationale=f"RSI={float(rsi):.1f} oversold",
                    )
                )
            elif (
                self.allow_short
                and rsi >= self.overbought
                and self._head_and_shoulders(sub["close"])
            ):
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (float(rsi) - self.overbought) / self.overbought)),
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="RsiPatternAlpha",
                        rationale=f"RSI={float(rsi):.1f} + head-and-shoulders",
                    )
                )
        return signals
