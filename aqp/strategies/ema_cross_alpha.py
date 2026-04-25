"""Fast/slow EMA cross alpha (Lean ``EmaCrossAlphaModel`` equivalent)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("EmaCrossAlphaModel")
class EmaCrossAlphaModel(IAlphaModel):
    """Long when fast EMA crosses above slow EMA; short on the inverse."""

    def __init__(self, fast: int = 20, slow: int = 50, allow_short: bool = True) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = int(fast)
        self.slow = int(slow)
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
            if len(sub) < self.slow + 2:
                continue
            ema_f = sub["close"].ewm(span=self.fast, adjust=False).mean()
            ema_s = sub["close"].ewm(span=self.slow, adjust=False).mean()
            spread = ema_f - ema_s
            prev, cur = spread.iloc[-2], spread.iloc[-1]
            close_last = float(sub["close"].iloc[-1])
            if pd.isna(prev) or pd.isna(cur):
                continue
            if prev <= 0 < cur:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(cur) / max(1e-6, close_last * 0.02))),
                        direction=Direction.LONG,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=0.6,
                        source="EmaCrossAlphaModel",
                        rationale=f"EMA{self.fast}/EMA{self.slow} bullish cross",
                    )
                )
            elif prev >= 0 > cur and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(cur) / max(1e-6, close_last * 0.02))),
                        direction=Direction.SHORT,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=0.6,
                        source="EmaCrossAlphaModel",
                        rationale=f"EMA{self.fast}/EMA{self.slow} bearish cross",
                    )
                )
        return signals
