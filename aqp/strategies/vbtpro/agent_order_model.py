"""Agent-driven :class:`IOrderModel` — emit precise orders, not just direction.

Where :class:`AgenticVbtAlpha` produces sparse Direction signals, this model
emits wide-format size + price arrays, which is the natural fit for the
vbt-pro engine's ``orders`` mode (``Portfolio.from_orders``).

Use this when:

- The agent emits both direction and a target ``size_pct``.
- The agent emits an explicit limit price (e.g. via a ``limit_price`` field
  in the decision payload).
- You want vbt-pro to honour multi-leg order semantics that ``from_signals``
  cannot express (e.g. simultaneous long-and-flat across symbols at one bar).
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.agents.trading.decision_cache import DecisionCache
from aqp.agents.trading.types import AgentDecision, TraderAction
from aqp.backtest.vbtpro.order_builder import OrderArrays
from aqp.core.interfaces import IOrderModel
from aqp.core.registry import register
from aqp.core.types import Symbol

logger = logging.getLogger(__name__)


@register("AgenticOrderModel", kind="execution")
class AgenticOrderModel(IOrderModel):
    """Build wide-format orders from cached agent decisions.

    Parameters
    ----------
    strategy_id:
        Logical id partitioning the :class:`DecisionCache`.
    cache_root:
        Optional cache root override.
    size_type:
        ``"targetpercent"`` (default) — size_pct interpreted as a target
        percent of equity. Other valid values: ``"amount"``,
        ``"percent"``, ``"value"``, ``"targetshares"``, ``"targetvalue"``.
    use_limit_price:
        When True, attempt to extract ``decision.limit_price`` and emit a
        ``price`` DataFrame; vbt-pro will treat the order as a limit order.
    min_confidence:
        Skip decisions below this confidence threshold.
    """

    def __init__(
        self,
        strategy_id: str = "default",
        *,
        cache_root: str | None = None,
        size_type: str = "targetpercent",
        use_limit_price: bool = False,
        min_confidence: float = 0.0,
    ) -> None:
        self.strategy_id = strategy_id
        self.cache = DecisionCache(root=cache_root, strategy_id=strategy_id)
        self.size_type = str(size_type)
        self.use_limit_price = bool(use_limit_price)
        self.min_confidence = float(min_confidence)

    def generate_orders(
        self,
        bars: pd.DataFrame,
        universe: list[Symbol],
        context: dict[str, Any],
    ) -> OrderArrays:
        close: pd.DataFrame = context.get("close")  # type: ignore[assignment]
        if close is None:
            close = (
                bars.copy()
                .assign(timestamp=lambda df: pd.to_datetime(df["timestamp"]))
                .pivot_table(
                    index="timestamp",
                    columns="vt_symbol",
                    values="close",
                    aggfunc="last",
                )
                .sort_index()
                .ffill()
            )

        size = pd.DataFrame(0.0, index=close.index, columns=close.columns)
        price: pd.DataFrame | None = (
            pd.DataFrame(float("nan"), index=close.index, columns=close.columns)
            if self.use_limit_price
            else None
        )

        for vt_symbol in close.columns:
            for ts in close.index:
                ts_py = ts.to_pydatetime()
                decision = self.cache.get(vt_symbol, ts_py)
                if decision is None:
                    continue
                signed_size = self._signed_size(decision)
                if signed_size == 0.0:
                    continue
                size.at[ts, vt_symbol] = signed_size
                if price is not None:
                    limit = self._limit_price(decision)
                    if limit is not None:
                        price.at[ts, vt_symbol] = limit

        return OrderArrays(
            size=size,
            price=price,
            size_type=self.size_type,
        )

    def _signed_size(self, decision: AgentDecision) -> float:
        if decision.confidence < self.min_confidence:
            return 0.0
        if decision.action == TraderAction.HOLD:
            return 0.0
        size = float(decision.size_pct or 0.0)
        if decision.action == TraderAction.BUY:
            return size
        if decision.action == TraderAction.SELL:
            return -size
        return 0.0

    def _limit_price(self, decision: AgentDecision) -> float | None:
        # ``AgentDecision`` does not have a typed ``limit_price``; check
        # extras / trader_plan / payload-style attributes opportunistically.
        for attr in ("limit_price", "price"):
            value = getattr(decision, attr, None)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    continue
        plan = getattr(decision, "trader_plan", None)
        if plan is not None:
            for attr in ("limit_price", "entry_price"):
                value = getattr(plan, attr, None)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
        return None


__all__ = ["AgenticOrderModel"]
