"""Mean-reversion alpha — the canonical baseline."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("MeanReversionAlpha")
class MeanReversionAlpha(IAlphaModel):
    """Bollinger-style z-score: long when z < -threshold, flat on reversion."""

    def __init__(self, lookback: int = 20, z_threshold: float = 2.0, hold_bars: int = 5) -> None:
        self.lookback = int(lookback)
        self.z_threshold = float(z_threshold)
        self.hold_bars = int(hold_bars)

    def generate_signals(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> list[Signal]:
        if bars.empty:
            return []

        signals: list[Signal] = []
        universe_set = {s.vt_symbol for s in universe}
        now = context.get("current_time")
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.lookback + 1:
                continue
            close = sub["close"]
            mean = close.rolling(self.lookback).mean()
            std = close.rolling(self.lookback).std()
            z = (close - mean) / std.replace(0, float("nan"))
            last = z.iloc[-1]
            if pd.isna(last):
                continue
            if last <= -self.z_threshold:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(abs(last) / self.z_threshold, 3.0) / 3.0),
                        direction=Direction.LONG,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(min(abs(last) / self.z_threshold, 2.0) / 2.0),
                        horizon_days=self.hold_bars,
                        source="MeanReversionAlpha",
                        rationale=f"z-score={last:.2f} at lookback={self.lookback}",
                    )
                )
            elif last >= self.z_threshold:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(abs(last) / self.z_threshold, 3.0) / 3.0),
                        direction=Direction.SHORT,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(min(abs(last) / self.z_threshold, 2.0) / 2.0),
                        horizon_days=self.hold_bars,
                        source="MeanReversionAlpha",
                        rationale=f"z-score={last:.2f} at lookback={self.lookback}",
                    )
                )
        return signals
