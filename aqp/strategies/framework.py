"""Lean-style 5-stage FrameworkAlgorithm.

Composes a ``UniverseSelectionModel``, ``AlphaModel``, ``PortfolioConstruction``,
``RiskManagement``, and ``ExecutionModel`` into a single strategy object the
backtest engine can call each bar.
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from typing import Any

import pandas as pd

from aqp.core.interfaces import (
    IAlphaModel,
    IExecutionModel,
    IPortfolioConstructionModel,
    IRiskManagementModel,
    IStrategy,
    IUniverseSelectionModel,
)
from aqp.core.registry import register
from aqp.core.types import BarData, OrderData, OrderRequest

logger = logging.getLogger(__name__)


@register("FrameworkAlgorithm")
class FrameworkAlgorithm(IStrategy):
    """Algorithm = Universe → Alpha → Portfolio → Risk → Execution."""

    def __init__(
        self,
        universe_model: IUniverseSelectionModel,
        alpha_model: IAlphaModel,
        portfolio_model: IPortfolioConstructionModel,
        risk_model: IRiskManagementModel,
        execution_model: IExecutionModel,
        strategy_id: str | None = None,
        rebalance_every: int = 1,
    ) -> None:
        self.universe_model = universe_model
        self.alpha_model = alpha_model
        self.portfolio_model = portfolio_model
        self.risk_model = risk_model
        self.execution_model = execution_model
        self.strategy_id = strategy_id or f"strat-{uuid.uuid4().hex[:8]}"
        self.rebalance_every = max(1, int(rebalance_every))
        self._timesteps_seen = 0
        self._last_rebalance_ts: Any = None

    def on_bar(self, bar: BarData, context: dict[str, Any]) -> Iterator[OrderRequest]:
        # Rebalance only ONCE per unique timestamp, regardless of how many
        # symbols the engine iterates through for that bar. This mirrors Lean's
        # ``OnData(Slice)`` where every symbol in a slice is handled together.
        if self._last_rebalance_ts == bar.timestamp:
            return iter(())
        self._last_rebalance_ts = bar.timestamp
        self._timesteps_seen += 1
        if self._timesteps_seen % self.rebalance_every != 0:
            return iter(())

        history: pd.DataFrame = context.get("history", pd.DataFrame())
        if history.empty:
            return iter(())

        universe = self.universe_model.select(bar.timestamp, context)
        context = {**context, "current_time": bar.timestamp, "strategy_id": self.strategy_id}
        signals = self.alpha_model.generate_signals(history, universe, context)
        targets = self.portfolio_model.construct(signals, context)
        targets = self.risk_model.evaluate(targets, context)
        orders = self.execution_model.execute(targets, context)

        for o in orders:
            if o.strategy_id is None:
                o.strategy_id = self.strategy_id
        return iter(orders)

    def on_order_update(self, order: OrderData) -> None:  # pragma: no cover — hook
        logger.debug("[%s] order update: %s %s", self.strategy_id, order.order_id, order.status)
