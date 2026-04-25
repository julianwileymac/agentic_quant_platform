"""backtesting.py ``SmaCross`` reference — ported as an :class:`IAlphaModel`.

Ref: ``inspiration/backtesting.py-master/doc/examples/Quick Start User Guide.py``.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("momentum", "reference", "backtesting.py")


@register("SmaCross")
class SmaCross(IAlphaModel):
    """Fast/slow SMA crossover — the canonical backtesting.py example."""

    def __init__(self, fast: int = 10, slow: int = 20, allow_short: bool = True) -> None:
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
        out: list[Signal] = []
        for vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            if vt_symbol not in universe_set:
                continue
            sub = sub.sort_values("timestamp")
            if len(sub) < self.slow + 2:
                continue
            close = sub["close"]
            ma1 = close.rolling(self.fast).mean()
            ma2 = close.rolling(self.slow).mean()
            prev = float(ma1.iloc[-2] - ma2.iloc[-2])
            cur = float(ma1.iloc[-1] - ma2.iloc[-1])
            ts = now or sub["timestamp"].iloc[-1]
            if prev <= 0 < cur:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.6,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.55,
                        source="SmaCross",
                        rationale=f"SMA{self.fast} crossed above SMA{self.slow}",
                    )
                )
            elif prev >= 0 > cur and self.allow_short:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.6,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.55,
                        source="SmaCross",
                        rationale=f"SMA{self.fast} crossed below SMA{self.slow}",
                    )
                )
        return out
