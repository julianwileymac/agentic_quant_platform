"""Shooting Star alpha — candle-pattern short.

Ref: ``inspiration/quant-trading-master/Shooting Star backtest.py``.

A shooting-star candle has a small real body near the period low, a long
upper shadow, and very little lower shadow, following an uptrend. We go
short on the bar following a confirmed shooting star.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("pattern", "reversal", "quant-trading")


@register("ShootingStarAlpha")
class ShootingStarAlpha(IAlphaModel):
    def __init__(
        self,
        uptrend_lookback: int = 5,
        body_ratio: float = 0.3,
        upper_ratio: float = 2.0,
        allow_short: bool = True,
    ) -> None:
        self.uptrend_lookback = int(uptrend_lookback)
        self.body_ratio = float(body_ratio)
        self.upper_ratio = float(upper_ratio)
        self.allow_short = bool(allow_short)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty or not self.allow_short:
            return []
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        signals: list[Signal] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.uptrend_lookback + 2:
                continue
            recent_close = sub["close"].tail(self.uptrend_lookback + 1)
            uptrend = (recent_close.diff().dropna() > 0).mean() >= 0.6
            if not uptrend:
                continue
            row = sub.iloc[-1]
            body = abs(row["close"] - row["open"])
            upper_shadow = row["high"] - max(row["close"], row["open"])
            lower_shadow = min(row["close"], row["open"]) - row["low"]
            rng = row["high"] - row["low"] if row["high"] != row["low"] else 1e-9
            if body / rng > self.body_ratio:
                continue
            if upper_shadow / max(body, 1e-9) < self.upper_ratio:
                continue
            if lower_shadow > body:
                continue
            signals.append(
                Signal(
                    symbol=Symbol.parse(vt_symbol),
                    strength=float(min(1.0, upper_shadow / rng)),
                    direction=Direction.SHORT,
                    timestamp=now or row["timestamp"],
                    confidence=0.55,
                    source="ShootingStarAlpha",
                    rationale=f"shooting star (upper/body={upper_shadow / max(body, 1e-9):.2f})",
                )
            )
        return signals
