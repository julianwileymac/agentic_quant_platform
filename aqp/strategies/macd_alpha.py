"""MACD crossover alpha (Lean ``MacdAlphaModel`` equivalent)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("MacdAlphaModel")
class MacdAlphaModel(IAlphaModel):
    """Long on bullish MACD crossover, short on bearish crossover."""

    def __init__(
        self,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        allow_short: bool = True,
    ) -> None:
        self.fast = int(fast)
        self.slow = int(slow)
        self.signal = int(signal)
        self.allow_short = bool(allow_short)

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
            if len(sub) < self.slow + self.signal:
                continue
            ema_fast = sub["close"].ewm(span=self.fast, adjust=False).mean()
            ema_slow = sub["close"].ewm(span=self.slow, adjust=False).mean()
            macd = ema_fast - ema_slow
            sig = macd.ewm(span=self.signal, adjust=False).mean()
            hist = macd - sig
            if len(hist) < 2 or pd.isna(hist.iloc[-1]) or pd.isna(hist.iloc[-2]):
                continue
            prev, cur = hist.iloc[-2], hist.iloc[-1]
            if prev <= 0 < cur:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(cur) / max(1e-6, sub["close"].iloc[-1] * 0.01))),
                        direction=Direction.LONG,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=0.7,
                        source="MacdAlphaModel",
                        rationale=f"MACD hist {prev:.3f}→{cur:.3f} (bullish cross)",
                    )
                )
            elif prev >= 0 > cur and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(cur) / max(1e-6, sub["close"].iloc[-1] * 0.01))),
                        direction=Direction.SHORT,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=0.7,
                        source="MacdAlphaModel",
                        rationale=f"MACD hist {prev:.3f}→{cur:.3f} (bearish cross)",
                    )
                )
        return signals
