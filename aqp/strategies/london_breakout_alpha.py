"""London Breakout alpha — Asia-session-range breakout.

Ref: ``inspiration/quant-trading-master/London Breakout backtest.py``.

The reference uses intraday minute bars and projects a range from the last
Tokyo hour (EST 2am) into the London open (EST 3am). At daily resolution
(our default), we approximate by breaking out of the previous day's range
at the first bar of the new session — flexible enough to stay useful on
daily data while still serving as a clear ported example.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("breakout", "fx", "quant-trading")


@register(
    "LondonBreakoutAlpha",
    kind="strategy",
    tags=STRATEGY_TAGS,
    source="quant_trading",
    category="breakout",
)
class LondonBreakoutAlpha(IAlphaModel):
    def __init__(
        self,
        risk_bps: int = 10,
        buffer_bps: int = 5,
        allow_short: bool = True,
    ) -> None:
        self.risk_bps = int(risk_bps)
        self.buffer_bps = int(buffer_bps)
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
            if len(sub) < 2:
                continue
            prev = sub.iloc[-2]
            curr = sub.iloc[-1]
            buffer = curr["open"] * self.buffer_bps / 10000.0
            up_break = float(curr["high"]) >= float(prev["high"]) + buffer
            dn_break = float(curr["low"]) <= float(prev["low"]) - buffer
            ts = now or curr["timestamp"]
            if up_break:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (curr["high"] - prev["high"]) / max(prev["high"], 1e-9))),
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.55,
                        source="LondonBreakoutAlpha",
                        rationale="upper breakout of Asia-session range",
                    )
                )
            elif dn_break and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, (prev["low"] - curr["low"]) / max(prev["low"], 1e-9))),
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.55,
                        source="LondonBreakoutAlpha",
                        rationale="lower breakout of Asia-session range",
                    )
                )
        return signals
