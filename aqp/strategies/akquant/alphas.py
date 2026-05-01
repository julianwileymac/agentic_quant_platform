"""akquant-main/examples strategy ports.

Many akquant patterns map directly to AQP's existing
:class:`FrameworkAlgorithm` + portfolio construction primitives. Where
that is the case the strategy class is a thin alpha that emits ranks,
and the portfolio model handles the rest.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.core.registry import register
from aqp.strategies.qtradex.alphas import BasicAlphaBase, _atr, _sma

logger = logging.getLogger(__name__)


@register("DualMovingAverageAlpha", source="akquant", category="trend")
class DualMovingAverageAlpha(BasicAlphaBase):
    name = "DualMovingAverageAlpha"

    def __init__(self, fast_window: int = 5, slow_window: int = 20) -> None:
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.min_history = slow_window * 3

    def signal_for_symbol(self, sub, context):
        close = sub["close"]
        fast = _sma(close, self.fast_window).iloc[-1]
        slow = _sma(close, self.slow_window).iloc[-1]
        if pd.isna(fast) or pd.isna(slow):
            return None
        if fast > slow * 1.001:
            return 1, 0.6, f"SMA{self.fast_window}>SMA{self.slow_window}"
        if fast < slow * 0.999:
            return -1, 0.6, f"SMA{self.fast_window}<SMA{self.slow_window}"
        return None


@register("AtrBreakoutAlpha", source="akquant", category="breakout")
class AtrBreakoutAlpha(BasicAlphaBase):
    name = "AtrBreakoutAlpha"

    def __init__(self, donchian_period: int = 20, atr_period: int = 14, atr_multiple: float = 1.0) -> None:
        self.donchian_period = donchian_period
        self.atr_period = atr_period
        self.atr_multiple = atr_multiple
        self.min_history = max(donchian_period, atr_period) * 2

    def signal_for_symbol(self, sub, context):
        high = sub["high"].rolling(self.donchian_period).max().iloc[-1]
        low = sub["low"].rolling(self.donchian_period).min().iloc[-1]
        atr = _atr(sub["high"], sub["low"], sub["close"], self.atr_period).iloc[-1]
        last = sub["close"].iloc[-1]
        if pd.isna(atr):
            return None
        if last > high - 0.1 * atr:
            return 1, 0.6, f"breakout high={high:.2f}"
        if last < low + 0.1 * atr:
            return -1, 0.6, f"breakdown low={low:.2f}"
        return None


@register("MomentumRotationAlpha", source="akquant", category="rotation")
class MomentumRotationAlpha(BasicAlphaBase):
    """Cross-sectional momentum — rank symbols by trailing return.

    Pair with :class:`MomentumRotationConstruction` (top-K) for the full
    rotation behaviour.
    """

    name = "MomentumRotationAlpha"

    def __init__(self, lookback: int = 60) -> None:
        self.lookback = lookback
        self.min_history = lookback

    def signal_for_symbol(self, sub, context):
        ret = sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback] - 1.0
        sign = 1 if ret > 0 else -1
        return sign, min(1.0, abs(ret)), f"{self.lookback}-bar return={ret:.4f}"


@register("BucketMomentumRotationAlpha", source="akquant", category="rotation")
class BucketMomentumRotationAlpha(MomentumRotationAlpha):
    """Bucketed momentum — rank within sector buckets.

    Buckets read from ``context["sector_map"]`` (``{vt_symbol: sector}``).
    Falls back to global momentum if no map provided.
    """

    name = "BucketMomentumRotationAlpha"

    def generate_signals(self, bars, universe, context):
        sector_map = context.get("sector_map", {})
        if not sector_map:
            return super().generate_signals(bars, universe, context)
        # Rank within each sector
        from aqp.core.types import Direction, Signal, Symbol
        signals = []
        by_sector: dict[str, list[tuple[str, float]]] = {}
        for vt, sector in sector_map.items():
            sub = bars[bars["vt_symbol"] == vt].sort_values("timestamp")
            if len(sub) < self.lookback:
                continue
            ret = sub["close"].iloc[-1] / sub["close"].iloc[-self.lookback] - 1.0
            by_sector.setdefault(sector, []).append((vt, ret))
        for sector, items in by_sector.items():
            ranked = sorted(items, key=lambda kv: kv[1], reverse=True)
            n = len(ranked)
            cutoff = max(1, n // 3)
            for vt, ret in ranked[:cutoff]:
                signals.append(Signal(symbol=Symbol.parse(vt), strength=min(1.0, abs(ret)), direction=Direction.LONG, source=self.name, rationale=f"sector={sector} top"))
            for vt, ret in ranked[-cutoff:]:
                signals.append(Signal(symbol=Symbol.parse(vt), strength=min(1.0, abs(ret)), direction=Direction.SHORT, source=self.name, rationale=f"sector={sector} bottom"))
        return signals


@register("TimerMomentumRotationAlpha", source="akquant", category="rotation")
class TimerMomentumRotationAlpha(MomentumRotationAlpha):
    """Momentum rotation that only rebalances on a fixed cadence.

    Rebalance cadence is enforced at the strategy / framework level via
    ``rebalance_every`` kwarg of :class:`FrameworkAlgorithm`. This alpha
    behaves identically to :class:`MomentumRotationAlpha`; the cadence
    is set in YAML.
    """

    name = "TimerMomentumRotationAlpha"


# ---------------------------------------------------------------------------
# Order-book aware demos (Grid, T+1, Futures Trend, Covered Call, ETF Grid)
# These leverage IStrategy semantics where state is needed.
# ---------------------------------------------------------------------------


from aqp.core.interfaces import IStrategy
from aqp.core.types import BarData, OrderData, OrderRequest


@register("GridTradingStrategy", source="akquant", category="grid")
class GridTradingStrategy(IStrategy):
    """Grid trading — buy on each lower grid level, sell on each upper.

    Stub implementation: emits zero orders by default; the engine should
    wire a stateful grid in production. We keep it simple to avoid
    coupling to the engine's order routing internals.
    """

    strategy_id = "grid_trading"

    def __init__(self, grid_step_pct: float = 0.02, n_levels: int = 5, qty_per_level: float = 10.0) -> None:
        self.grid_step_pct = grid_step_pct
        self.n_levels = n_levels
        self.qty_per_level = qty_per_level

    def on_bar(self, bar: BarData, context: dict[str, Any]):
        return iter(())

    def on_order_update(self, order: OrderData) -> None:
        return None


@register("TPlusOneStrategy", source="akquant", category="market_specific")
class TPlusOneStrategy(IStrategy):
    """China T+1 settlement aware strategy stub.

    Marker for UI / docs; concrete fill enforcement lives in the
    paper / live brokerage layer.
    """

    strategy_id = "t_plus_one"

    def __init__(self) -> None:
        return

    def on_bar(self, bar: BarData, context: dict[str, Any]):
        return iter(())

    def on_order_update(self, order: OrderData) -> None:
        return None


@register("FuturesTrendAlpha", source="akquant", category="trend")
class FuturesTrendAlpha(BasicAlphaBase):
    """Trend following on continuous futures — long when SMA(20) > SMA(60)."""

    name = "FuturesTrendAlpha"

    def __init__(self) -> None:
        self.min_history = 80

    def signal_for_symbol(self, sub, context):
        sma20 = _sma(sub["close"], 20).iloc[-1]
        sma60 = _sma(sub["close"], 60).iloc[-1]
        if pd.isna(sma60):
            return None
        if sma20 > sma60:
            return 1, 0.6, "SMA20>SMA60"
        if sma20 < sma60:
            return -1, 0.6, "SMA20<SMA60"
        return None


@register("CoveredCallStrategy", source="akquant", category="options")
class CoveredCallStrategy(IStrategy):
    """Covered call stub — holds underlying + sells calls. Engine-pending."""

    strategy_id = "covered_call"

    def __init__(self) -> None:
        return

    def on_bar(self, bar: BarData, context: dict[str, Any]):
        return iter(())

    def on_order_update(self, order: OrderData) -> None:
        return None


@register("ETFGridStrategy", source="akquant", category="grid")
class ETFGridStrategy(GridTradingStrategy):
    strategy_id = "etf_grid"


@register("SixtyFortyRebalanceStrategy", source="akquant", category="rebalance")
class SixtyFortyRebalanceStrategy(BasicAlphaBase):
    """Emits LONG signals for both equity and bond legs.

    Pair with :class:`SixtyForty` portfolio construction model for the
    actual 60/40 weighting.
    """

    name = "SixtyFortyRebalanceStrategy"

    def __init__(self, equity_symbol: str = "SPY.NASDAQ", bond_symbol: str = "AGG.NASDAQ") -> None:
        self.equity_symbol = equity_symbol
        self.bond_symbol = bond_symbol
        self.min_history = 1

    def generate_signals(self, bars, universe, context):
        from aqp.core.types import Direction, Signal, Symbol
        return [
            Signal(symbol=Symbol.parse(self.equity_symbol), strength=0.6, direction=Direction.LONG, source=self.name, rationale="equity_leg"),
            Signal(symbol=Symbol.parse(self.bond_symbol), strength=0.4, direction=Direction.LONG, source=self.name, rationale="bond_leg"),
        ]


@register("TargetWeightsRebalanceStrategy", source="akquant", category="rebalance")
class TargetWeightsRebalanceStrategy(BasicAlphaBase):
    """Emit equal-weight LONG signals for a fixed symbol list.

    Actual weights come from :class:`TargetWeightsRebalancer`
    portfolio construction model (read from YAML).
    """

    name = "TargetWeightsRebalanceStrategy"

    def __init__(self, symbols: list[str] | None = None) -> None:
        self.symbols = list(symbols or [])
        self.min_history = 1

    def generate_signals(self, bars, universe, context):
        from aqp.core.types import Direction, Signal, Symbol
        targets = self.symbols or [s.vt_symbol for s in universe]
        return [
            Signal(symbol=Symbol.parse(s), strength=0.5, direction=Direction.LONG, source=self.name, rationale="target_weight")
            for s in targets
        ]
