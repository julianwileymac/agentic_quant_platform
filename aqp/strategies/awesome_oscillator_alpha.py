"""Awesome Oscillator alpha — SMA5 vs SMA34 of the median price + saucer rule.

Ref: ``inspiration/quant-trading-master/Awesome Oscillator backtest.py``.

The Awesome Oscillator (Bill Williams) measures momentum as the difference
between a 5-period SMA of ``(high+low)/2`` and a 34-period SMA of the same
series. The 'saucer' pattern refines the raw cross by requiring the AO
histogram to turn up / down through three consecutive bars confirming the
signal direction.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("momentum", "oscillator", "quant-trading")


@register(
    "AwesomeOscillatorAlpha",
    kind="strategy",
    tags=STRATEGY_TAGS,
    source="quant_trading",
    category="momentum",
)
class AwesomeOscillatorAlpha(IAlphaModel):
    def __init__(
        self,
        fast: int = 5,
        slow: int = 34,
        use_saucer: bool = True,
        allow_short: bool = True,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = int(fast)
        self.slow = int(slow)
        self.use_saucer = bool(use_saucer)
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
            if len(sub) < self.slow + 3:
                continue
            mid = (sub["high"] + sub["low"]) / 2.0
            fast_ma = mid.rolling(self.fast).mean()
            slow_ma = mid.rolling(self.slow).mean()
            ao = (fast_ma - slow_ma).dropna()
            if len(ao) < 3:
                continue
            a0 = float(ao.iloc[-1])
            a1 = float(ao.iloc[-2])
            a2 = float(ao.iloc[-3])

            long_cross = a1 <= 0 < a0
            short_cross = a1 >= 0 > a0
            if self.use_saucer:
                long_saucer = a0 > a1 > a2 and a0 > 0
                short_saucer = a0 < a1 < a2 and a0 < 0
            else:
                long_saucer = False
                short_saucer = False
            ts = now or sub["timestamp"].iloc[-1]

            if long_cross or long_saucer:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(a0) / max(1e-6, float(sub["close"].iloc[-1]) * 0.02))),
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="AwesomeOscillatorAlpha",
                        rationale=f"AO={a0:.3f} (cross={long_cross}, saucer={long_saucer})",
                    )
                )
            elif (short_cross or short_saucer) and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, abs(a0) / max(1e-6, float(sub["close"].iloc[-1]) * 0.02))),
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="AwesomeOscillatorAlpha",
                        rationale=f"AO={a0:.3f} (cross={short_cross}, saucer={short_saucer})",
                    )
                )
        return signals
