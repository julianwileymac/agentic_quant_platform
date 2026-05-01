"""stock-analysis-engine strategy ports.

Adapters for the indicator-vote pattern and a thin user-callback bridge.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pandas as pd

from aqp.core.interfaces import IAlphaModel, IStrategy
from aqp.core.registry import register
from aqp.core.types import BarData, Direction, OrderData, OrderRequest, Signal, Symbol
from aqp.data.indicators_zoo import IndicatorZoo
from aqp.strategies.qtradex.alphas import BasicAlphaBase

logger = logging.getLogger(__name__)


@register("StockAnalysisEngineAdapterStrategy", source="sae", category="adapter")
class StockAnalysisEngineAdapterStrategy(IStrategy):
    """Wraps an arbitrary user ``process_fn(dataset) -> (buy_count, sell_count)``.

    Use to port an existing ``BaseAlgo.process`` function from
    ``analysis_engine`` without rewriting it. ``process_fn`` receives a
    dict with ``bars`` (current symbol's tail of bars) and ``context``
    (the engine's bar / position context) and returns a tuple ``(buy, sell)``
    of integer counts.
    """

    strategy_id = "sae_adapter"

    def __init__(
        self,
        process_fn: Callable[[dict[str, Any]], tuple[int, int]] | None = None,
        min_buy: int = 3,
        min_sell: int = 3,
    ) -> None:
        self.process_fn = process_fn
        self.min_buy = min_buy
        self.min_sell = min_sell

    def on_bar(self, bar: BarData, context: dict[str, Any]) -> Iterator[OrderRequest]:
        if self.process_fn is None:
            return iter(())
        try:
            buy_count, sell_count = self.process_fn({"bar": bar, "context": context})
        except Exception:  # noqa: BLE001
            logger.exception("sae_adapter process_fn failed")
            return iter(())
        if buy_count >= self.min_buy:
            logger.debug("sae_adapter buy signal for %s", bar.symbol.vt_symbol)
        return iter(())

    def on_order_update(self, order: OrderData) -> None:
        return None


@register("IndicatorVoteAlpha", source="sae", category="consensus")
class IndicatorVoteAlpha(BasicAlphaBase):
    """Generic indicator-vote alpha (port of ``trade_off_indicator_buy_and_sell_signals``).

    Configure with a list of indicator specs (e.g. ``["SMA:20", "RSI:14",
    "MACD"]``) and threshold counts. Each indicator that fires bullish
    counts +1; bearish counts -1.
    """

    name = "IndicatorVoteAlpha"

    def __init__(
        self,
        indicators: list[str] | None = None,
        min_buy_count: int = 3,
        min_sell_count: int = 3,
    ) -> None:
        self.indicators = indicators or ["SMA:20", "EMA:50", "RSI:14", "MACD", "BBands:20"]
        self.min_buy_count = min_buy_count
        self.min_sell_count = min_sell_count
        self.zoo = IndicatorZoo(self.indicators)
        self.min_history = 60

    def signal_for_symbol(self, sub, context):
        result = self.zoo.transform(sub.assign(vt_symbol=sub.iloc[0].get("vt_symbol", "X.LOCAL")))
        last = result.iloc[-1]
        last_close = float(last.get("close", float("nan")))
        if pd.isna(last_close):
            return None
        bull_votes = 0
        bear_votes = 0
        for col in result.columns:
            if col in {"open", "high", "low", "close", "volume", "timestamp", "vt_symbol"}:
                continue
            val = last.get(col)
            try:
                v = float(val)
            except Exception:  # noqa: BLE001
                continue
            if pd.isna(v):
                continue
            if "RSI" in col:
                if v < 30:
                    bull_votes += 1
                if v > 70:
                    bear_votes += 1
            elif "SMA" in col or "EMA" in col:
                if last_close > v:
                    bull_votes += 1
                else:
                    bear_votes += 1
        if bull_votes >= self.min_buy_count:
            return 1, min(1.0, bull_votes / max(len(self.indicators), 1)), f"bull votes={bull_votes}"
        if bear_votes >= self.min_sell_count:
            return -1, min(1.0, bear_votes / max(len(self.indicators), 1)), f"bear votes={bear_votes}"
        return None


@register("OptionSpreadStrategy", source="sae", category="options")
class OptionSpreadStrategy(IStrategy):
    """Vertical option spread placeholder strategy.

    Real fills require an options-aware brokerage. This stub records the
    intended spread parameters so downstream tooling (e.g.
    ``aqp.options.spreads.vertical_spread``) can compute P&L.
    """

    strategy_id = "option_spread"

    def __init__(
        self,
        long_strike: float = 100.0,
        short_strike: float = 110.0,
        long_premium: float = 5.0,
        short_premium: float = 2.0,
        is_call: bool = True,
    ) -> None:
        self.long_strike = long_strike
        self.short_strike = short_strike
        self.long_premium = long_premium
        self.short_premium = short_premium
        self.is_call = is_call

    def on_bar(self, bar: BarData, context: dict[str, Any]):
        return iter(())

    def on_order_update(self, order: OrderData) -> None:
        return None
