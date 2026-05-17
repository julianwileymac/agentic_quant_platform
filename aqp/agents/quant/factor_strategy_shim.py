"""``FactorStrategyShim`` — thin event-driven strategy that emits a factor signal.

Used internally by :class:`aqp.agents.quant.AlphaResearcher.evaluate`
to backtest a compiled :class:`FactorNode` without requiring the
agent author to hand-write a strategy class. The shim:

1. Evaluates the factor on each new bar (using the rolling history).
2. Maps the sign of the factor into a target weight
   ``{+1.0 if factor > 0 else -1.0 if factor < 0 else 0.0}``.
3. Emits a single :class:`OrderRequest` per bar to rebalance toward
   the target weight (long-only by default; set ``allow_short=True``
   for long/short).

The shim is the simplest reward bridge the FinRL-X loop can use; a
researcher can substitute a richer Strategy implementation by
passing it explicitly to ``AlphaResearcher(backtest_engine=...)``.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.core.types import (
    OrderRequest,
    OrderSide,
    OrderType,
    Symbol,
)
from aqp.data.expressions_dsl import FactorNode

logger = logging.getLogger(__name__)


class FactorStrategyShim:
    """Per-bar event-driven strategy that rebalances on factor sign.

    Compatible with the :class:`aqp.backtest.engine.EventDrivenBacktester`
    contract (``on_bar(bar, context) -> list[OrderRequest]``).
    """

    def __init__(
        self,
        *,
        factor: FactorNode,
        allow_short: bool = False,
        target_weight: float = 1.0,
        rebalance_threshold: float = 0.05,
    ) -> None:
        self.factor = factor
        self.allow_short = bool(allow_short)
        self.target_weight = float(target_weight)
        self.rebalance_threshold = float(rebalance_threshold)
        self._last_target: float = 0.0
        self._history_by_symbol: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ engine hook

    def on_bar(self, bar: Any, context: dict[str, Any]) -> list[OrderRequest]:
        # Maintain a rolling per-symbol history so the factor has
        # enough lookback to evaluate. The event-driven engine
        # provides bars one timestamp at a time.
        sym_key = bar.symbol.vt_symbol
        prev = self._history_by_symbol.get(sym_key)
        row = {
            "timestamp": pd.Timestamp(bar.timestamp),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        }
        df = pd.concat([prev, pd.DataFrame([row])], ignore_index=True) if prev is not None else pd.DataFrame([row])
        self._history_by_symbol[sym_key] = df
        try:
            series = self.factor.compute(df)
        except Exception:
            return []
        if series is None or series.empty:
            return []
        last_value = float(series.iloc[-1])
        if not (last_value == last_value):
            return []
        if last_value > 0:
            target = self.target_weight
        elif last_value < 0 and self.allow_short:
            target = -self.target_weight
        else:
            target = 0.0
        if abs(target - self._last_target) < self.rebalance_threshold:
            return []
        # Translate weight delta into a market-order on the bar's
        # close. Quantity sign encodes side; the engine handles the
        # cheat-on-open fill against the next bar.
        equity = float(context.get("equity", 100_000.0) or 100_000.0)
        price = float(bar.close)
        if price <= 0:
            return []
        delta_notional = (target - self._last_target) * equity
        qty = abs(delta_notional / price)
        if qty <= 0:
            return []
        side = OrderSide.BUY if delta_notional > 0 else OrderSide.SELL
        request = OrderRequest(
            symbol=Symbol.parse(sym_key) if isinstance(sym_key, str) else bar.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=float(qty),
            price=None,
            reference="factor_shim",
        )
        self._last_target = target
        return [request]


__all__ = ["FactorStrategyShim"]
