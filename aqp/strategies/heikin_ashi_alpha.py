"""Heikin-Ashi alpha — marubozu-style reversal pattern.

Ref: ``inspiration/quant-trading-master/Heikin-Ashi backtest.py``.

The Heikin-Ashi transform smooths the raw OHLC into a cleaner trend
series. We look for a bullish "marubozu" (open == low, close high in the
body) after a prior bearish HA candle to emit a long signal (inverse for
short).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("pattern", "reversal", "quant-trading")


def _heikin_ashi(bars: pd.DataFrame) -> pd.DataFrame:
    ha = bars.copy()
    ha_close = (bars["open"] + bars["high"] + bars["low"] + bars["close"]) / 4.0
    ha_open = bars["open"].copy()
    ha_open.iloc[0] = (bars["open"].iloc[0] + bars["close"].iloc[0]) / 2.0
    for i in range(1, len(bars)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2.0
    ha_high = pd.concat([bars["high"], ha_open, ha_close], axis=1).max(axis=1)
    ha_low = pd.concat([bars["low"], ha_open, ha_close], axis=1).min(axis=1)
    ha["ha_open"] = ha_open.values
    ha["ha_high"] = ha_high.values
    ha["ha_low"] = ha_low.values
    ha["ha_close"] = ha_close.values
    return ha


@register("HeikinAshiAlpha")
class HeikinAshiAlpha(IAlphaModel):
    def __init__(
        self,
        body_threshold: float = 0.6,
        allow_short: bool = True,
    ) -> None:
        self.body_threshold = float(body_threshold)
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
            if len(sub) < 3:
                continue
            ha = _heikin_ashi(sub)
            ho = ha["ha_open"].iloc[-1]
            hc = ha["ha_close"].iloc[-1]
            hh = ha["ha_high"].iloc[-1]
            hl = ha["ha_low"].iloc[-1]
            prev_bearish = ha["ha_close"].iloc[-2] < ha["ha_open"].iloc[-2]
            prev_bullish = ha["ha_close"].iloc[-2] > ha["ha_open"].iloc[-2]
            rng = hh - hl if hh != hl else 1e-9
            body = abs(hc - ho) / rng

            ts = now or sub["timestamp"].iloc[-1]
            if hc > ho and body >= self.body_threshold and prev_bearish:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, body)),
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.6,
                        source="HeikinAshiAlpha",
                        rationale=f"HA bullish marubozu (body={body:.2f})",
                    )
                )
            elif hc < ho and body >= self.body_threshold and prev_bullish and self.allow_short:
                signals.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=float(min(1.0, body)),
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.6,
                        source="HeikinAshiAlpha",
                        rationale=f"HA bearish marubozu (body={body:.2f})",
                    )
                )
        return signals
