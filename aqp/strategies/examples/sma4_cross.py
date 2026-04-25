"""backtesting.py ``Sma4Cross`` — trend filter + entry/exit crossovers.

Ref: ``inspiration/backtesting.py-master/doc/examples/Parameter Heatmap & Optimization.py``.

Two SMAs (``n1`` / ``n2``) form the trend filter; two more (``n_enter`` /
``n_exit``) time the entry and exit. Goes long only when both the entry
crossover and the trend filter are bullish (mirror for short).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("momentum", "reference", "backtesting.py")


@register("Sma4Cross")
class Sma4Cross(IAlphaModel):
    def __init__(
        self,
        n1: int = 50,
        n2: int = 100,
        n_enter: int = 20,
        n_exit: int = 10,
        allow_short: bool = True,
    ) -> None:
        self.n1 = int(n1)
        self.n2 = int(n2)
        self.n_enter = int(n_enter)
        self.n_exit = int(n_exit)
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
            if len(sub) < max(self.n1, self.n2) + 2:
                continue
            close = sub["close"]
            sma1 = close.rolling(self.n1).mean()
            sma2 = close.rolling(self.n2).mean()
            enter = close.rolling(self.n_enter).mean()
            exit_ = close.rolling(self.n_exit).mean()
            trend_up = float(sma1.iloc[-1]) > float(sma2.iloc[-1])
            trend_dn = float(sma1.iloc[-1]) < float(sma2.iloc[-1])
            prev = float(enter.iloc[-2] - exit_.iloc[-2])
            cur = float(enter.iloc[-1] - exit_.iloc[-1])
            ts = now or sub["timestamp"].iloc[-1]
            if trend_up and prev <= 0 < cur:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.65,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="Sma4Cross",
                        rationale="trend up + enter-SMA crossed above exit-SMA",
                    )
                )
            elif trend_dn and prev >= 0 > cur and self.allow_short:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.65,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="Sma4Cross",
                        rationale="trend down + enter-SMA crossed below exit-SMA",
                    )
                )
        return out
