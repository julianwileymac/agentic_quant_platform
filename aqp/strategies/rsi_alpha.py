"""RSI oscillator alpha (Lean ``RsiAlphaModel`` equivalent)."""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol


@register("RsiAlphaModel")
class RsiAlphaModel(IAlphaModel):
    """Long when RSI < oversold threshold, short when > overbought.

    Uses Wilder's RSI on the close column. Produces one ``Signal`` per
    symbol whose ``strength`` is the normalized distance past the
    threshold (capped at 1).
    """

    def __init__(
        self,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        allow_short: bool = True,
    ) -> None:
        self.period = int(period)
        self.oversold = float(oversold)
        self.overbought = float(overbought)
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
            if len(sub) <= self.period:
                continue
            delta = sub["close"].diff()
            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)
            avg_gain = gain.rolling(self.period).mean()
            avg_loss = loss.rolling(self.period).mean().replace(0, float("nan"))
            rs = avg_gain / avg_loss
            rsi_series = 100 - (100 / (1 + rs))
            rsi = rsi_series.iloc[-1]
            if pd.isna(rsi):
                continue
            if rsi <= self.oversold:
                strength = min(1.0, (self.oversold - rsi) / self.oversold)
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(strength),
                        direction=Direction.LONG,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(strength),
                        source="RsiAlphaModel",
                        rationale=f"RSI={rsi:.1f} < {self.oversold}",
                    )
                )
            elif rsi >= self.overbought and self.allow_short:
                strength = min(1.0, (rsi - self.overbought) / (100 - self.overbought))
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(strength),
                        direction=Direction.SHORT,
                        timestamp=now or sub["timestamp"].iloc[-1],
                        confidence=float(strength),
                        source="RsiAlphaModel",
                        rationale=f"RSI={rsi:.1f} > {self.overbought}",
                    )
                )
        return signals
