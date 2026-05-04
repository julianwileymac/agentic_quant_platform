"""Bollinger 'W' (double-bottom) pattern alpha.

Ref: ``inspiration/quant-trading-master/Bollinger Bands Pattern Recognition backtest.py``.

Scans a rolling window of bars for a W pattern: two local minima with
comparable lows, both touching or breaking the lower band, followed by
price breaking above the middle band. Mirror logic for the inverse 'M'
pattern on the short side.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("pattern", "mean-reversion", "quant-trading")


@register(
    "BollingerWAlpha",
    kind="strategy",
    tags=STRATEGY_TAGS,
    source="quant_trading",
    category="pattern",
)
class BollingerWAlpha(IAlphaModel):
    def __init__(
        self,
        period: int = 20,
        num_std: float = 2.0,
        scan_window: int = 75,
        min_bottoms: int = 2,
        allow_short: bool = True,
    ) -> None:
        self.period = int(period)
        self.num_std = float(num_std)
        self.scan_window = int(scan_window)
        self.min_bottoms = int(min_bottoms)
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
            if len(sub) < max(self.period + 5, self.scan_window):
                continue
            close = sub["close"]
            mid = close.rolling(self.period).mean()
            std = close.rolling(self.period).std(ddof=0)
            upper = mid + self.num_std * std
            lower = mid - self.num_std * std

            window_lower = lower.tail(self.scan_window)
            window_mid = mid.tail(self.scan_window)
            window_upper = upper.tail(self.scan_window)
            window_close = close.tail(self.scan_window)

            bottoms = int((window_close <= window_lower).sum())
            tops = int((window_close >= window_upper).sum())

            ts = now or sub["timestamp"].iloc[-1]
            if bottoms >= self.min_bottoms and float(window_close.iloc[-1]) > float(window_mid.iloc[-1]):
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.7,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.55,
                        source="BollingerWAlpha",
                        rationale=f"W pattern ({bottoms} taps) — close > mid band",
                    )
                )
            elif (
                self.allow_short
                and tops >= self.min_bottoms
                and float(window_close.iloc[-1]) < float(window_mid.iloc[-1])
            ):
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.7,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.55,
                        source="BollingerWAlpha",
                        rationale=f"M pattern ({tops} taps) — close < mid band",
                    )
                )
        return signals
