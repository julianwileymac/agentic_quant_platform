"""ATR trailing-stop alpha — ported from backtesting.py's Strategies Library.

Ref: ``inspiration/backtesting.py-master/doc/examples/Strategies Library.py``.

Pairs a short-window SMA cross entry with an ATR-based trailing stop
expressed as a :class:`Signal` with :class:`Direction.NET` when the stop
fires. The Portfolio stage should interpret ``NET`` as flat.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("momentum", "trailing-stop", "reference")


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period).mean()


@register("TrailingATRAlpha")
class TrailingATRAlpha(IAlphaModel):
    def __init__(
        self,
        fast: int = 10,
        slow: int = 20,
        atr_period: int = 14,
        atr_multiple: float = 6.0,
    ) -> None:
        self.fast = int(fast)
        self.slow = int(slow)
        self.atr_period = int(atr_period)
        self.atr_multiple = float(atr_multiple)
        self._state: dict[str, tuple[Direction, float]] = {}

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
            if len(sub) < max(self.slow, self.atr_period) + 2:
                continue
            close = sub["close"]
            fast_ma = close.rolling(self.fast).mean()
            slow_ma = close.rolling(self.slow).mean()
            atr = _atr(sub["high"], sub["low"], close, self.atr_period)
            prev = float(fast_ma.iloc[-2] - slow_ma.iloc[-2])
            cur = float(fast_ma.iloc[-1] - slow_ma.iloc[-1])
            c_now = float(close.iloc[-1])
            a_now = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0
            ts = now or sub["timestamp"].iloc[-1]

            state = self._state.get(vt_symbol)
            if state is not None:
                direction, stop = state
                # Trail in favour of the open position.
                if direction == Direction.LONG:
                    stop = max(stop, c_now - self.atr_multiple * a_now)
                    if c_now <= stop:
                        out.append(
                            Signal(
                                symbol=Symbol.parse(vt_symbol),
                                strength=0.0,
                                direction=Direction.NET,
                                timestamp=ts,
                                confidence=1.0,
                                source="TrailingATRAlpha",
                                rationale="ATR trail hit (long)",
                            )
                        )
                        self._state.pop(vt_symbol, None)
                        continue
                    self._state[vt_symbol] = (direction, stop)
                else:
                    stop = min(stop, c_now + self.atr_multiple * a_now)
                    if c_now >= stop:
                        out.append(
                            Signal(
                                symbol=Symbol.parse(vt_symbol),
                                strength=0.0,
                                direction=Direction.NET,
                                timestamp=ts,
                                confidence=1.0,
                                source="TrailingATRAlpha",
                                rationale="ATR trail hit (short)",
                            )
                        )
                        self._state.pop(vt_symbol, None)
                        continue
                    self._state[vt_symbol] = (direction, stop)

            if prev <= 0 < cur:
                self._state[vt_symbol] = (Direction.LONG, c_now - self.atr_multiple * a_now)
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.65,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="TrailingATRAlpha",
                        rationale=f"SMA{self.fast} crossed SMA{self.slow} (ATR trail set)",
                    )
                )
            elif prev >= 0 > cur:
                self._state[vt_symbol] = (Direction.SHORT, c_now + self.atr_multiple * a_now)
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.65,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="TrailingATRAlpha",
                        rationale=f"SMA{self.fast} crossed SMA{self.slow} (ATR trail set)",
                    )
                )
        return out
