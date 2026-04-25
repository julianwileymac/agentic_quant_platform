"""Dual Thrust alpha — intraday range-breakout.

Ref: ``inspiration/quant-trading-master/Dual Thrust backtest.py``.

Dual Thrust builds a daily range ``R`` from ``max(high) - min(close)`` and
``max(close) - min(low)`` over a lookback, then defines two break levels
relative to today's open: ``upper = open + k1*R`` and ``lower = open - k2*R``.
Crossing the upper level goes long; crossing the lower goes short.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("intraday", "breakout", "quant-trading")


@register("DualThrustAlpha")
class DualThrustAlpha(IAlphaModel):
    def __init__(
        self,
        lookback: int = 4,
        k1: float = 0.5,
        k2: float = 0.5,
        allow_short: bool = True,
    ) -> None:
        self.lookback = int(lookback)
        self.k1 = float(k1)
        self.k2 = float(k2)
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
            if len(sub) < self.lookback + 2:
                continue
            window = sub.iloc[-(self.lookback + 1) : -1]
            hh = window["high"].max()
            lc = window["close"].min()
            hc = window["close"].max()
            ll = window["low"].min()
            rng = max(hh - lc, hc - ll)
            if rng <= 0:
                continue
            open_today = float(sub["open"].iloc[-1])
            high_today = float(sub["high"].iloc[-1])
            low_today = float(sub["low"].iloc[-1])
            upper = open_today + self.k1 * rng
            lower = open_today - self.k2 * rng
            ts = now or sub["timestamp"].iloc[-1]

            if high_today >= upper:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (high_today - upper) / max(rng, 1e-9))),
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="DualThrustAlpha",
                        rationale=f"high {high_today:.2f} >= upper {upper:.2f}",
                    )
                )
            elif low_today <= lower and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (lower - low_today) / max(rng, 1e-9))),
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="DualThrustAlpha",
                        rationale=f"low {low_today:.2f} <= lower {lower:.2f}",
                    )
                )
        return signals
