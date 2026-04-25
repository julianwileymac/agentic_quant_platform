"""BaseAlgo example port — stock-analysis-engine minute demo.

Ref: ``inspiration/stock-analysis-engine-master/analysis_engine/mocks/example_algo_minute.py``.

The reference flows day/minute bars through ``BaseAlgo.handle_data`` and
dispatches to ``process`` for signal logic. We port the minimal "buy on
oversold, sell on overbought" template that ships with SAE as a showcase
of a linked indicator → decision → order pipeline.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel
from aqp.core.registry import register
from aqp.core.types import Direction, Signal, Symbol

STRATEGY_TAGS = ("reference", "stock-analysis-engine")


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)


@register("BaseAlgoExample")
class BaseAlgoExample(IAlphaModel):
    """Minimal BaseAlgo template: RSI-based buy/sell with SMA trend filter."""

    def __init__(
        self,
        rsi_period: int = 14,
        trend_period: int = 50,
        rsi_buy: float = 35.0,
        rsi_sell: float = 65.0,
        allow_short: bool = True,
    ) -> None:
        self.rsi_period = int(rsi_period)
        self.trend_period = int(trend_period)
        self.rsi_buy = float(rsi_buy)
        self.rsi_sell = float(rsi_sell)
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
            if len(sub) < max(self.rsi_period, self.trend_period) + 2:
                continue
            close = sub["close"]
            rsi = _rsi(close, self.rsi_period).iloc[-1]
            trend = close.rolling(self.trend_period).mean().iloc[-1]
            c_now = float(close.iloc[-1])
            ts = now or sub["timestamp"].iloc[-1]
            if pd.isna(rsi) or pd.isna(trend):
                continue
            uptrend = c_now > float(trend)
            if rsi <= self.rsi_buy and uptrend:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.6,
                        direction=Direction.LONG,
                        timestamp=ts,
                        confidence=0.55,
                        source="BaseAlgoExample",
                        rationale=f"RSI={float(rsi):.1f} + uptrend",
                    )
                )
            elif rsi >= self.rsi_sell and not uptrend and self.allow_short:
                out.append(
                    Signal(
                        symbol=Symbol.parse(vt_symbol),
                        strength=0.6,
                        direction=Direction.SHORT,
                        timestamp=ts,
                        confidence=0.55,
                        source="BaseAlgoExample",
                        rationale=f"RSI={float(rsi):.1f} + downtrend",
                    )
                )
        return out
