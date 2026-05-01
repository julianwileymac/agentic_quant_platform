"""Lean-style 5-stage FrameworkAlgorithm.

Composes a ``UniverseSelectionModel``, ``AlphaModel``, ``PortfolioConstruction``,
``RiskManagement``, and ``ExecutionModel`` into a single strategy object the
backtest engine can call each bar.

Events
------

When run inside the Phase 1 ``EventDrivenBacktester``, the engine consumes
``MarketEvent``s from a central ``deque`` and dispatches the slice to either
:meth:`on_data` (preferred) or :meth:`on_bar`. After execution the engine
inspects ``self._last_signals`` to construct a ``SignalEvent`` for the
event log; this keeps the IStrategy contract unchanged while still exposing
the full alpha → portfolio → risk → execution decision graph for replay.
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
from aqp.core.slice import Slice
from aqp.core.types import BarData, OrderData, OrderRequest, Signal

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
        # Phase 1 event-bus contract: the engine reads this list at the end
        # of each timestamp to construct a ``SignalEvent``. The engine clears
        # it after consumption so subsequent timestamps don't re-emit.
        self._last_signals: list[Signal] = []
        self._last_targets: list[Any] = []

    def _step(
        self,
        timestamp: Any,
        context: dict[str, Any],
    ) -> list[OrderRequest]:
        """Run the 5-stage pipeline once for ``timestamp``.

        Captures intermediate ``Signal`` and ``PortfolioTarget`` rows on the
        instance so the event-driven engine can emit them as ``SignalEvent``s
        in the event log. Returns the final ``OrderRequest`` list.
        """
        if self._last_rebalance_ts == timestamp:
            return []
        self._last_rebalance_ts = timestamp
        self._timesteps_seen += 1
        if self._timesteps_seen % self.rebalance_every != 0:
            return []

        history: pd.DataFrame = context.get("history", pd.DataFrame())
        if history.empty:
            return []

        universe = self.universe_model.select(timestamp, context)
        ctx = {
            **context,
            "current_time": timestamp,
            "strategy_id": self.strategy_id,
        }
        signals = self.alpha_model.generate_signals(history, universe, ctx)
        # Capture for the engine's SignalEvent emission. ``signals`` may be a
        # generator; materialise once.
        self._last_signals = list(signals)
        targets = self.portfolio_model.construct(self._last_signals, ctx)
        targets = self.risk_model.evaluate(targets, ctx)
        self._last_targets = list(targets)
        orders = list(self.execution_model.execute(self._last_targets, ctx))
        for o in orders:
            if o.strategy_id is None:
                o.strategy_id = self.strategy_id
        return orders

    def on_bar(self, bar: BarData, context: dict[str, Any]) -> Iterator[OrderRequest]:
        # Per-symbol entry point. The engine guarantees ``on_data`` is called
        # in preference to ``on_bar`` for the slice-aware path, so this branch
        # is the legacy fallback.
        return iter(self._step(bar.timestamp, context))

    def on_data(self, slice_: Slice, context: dict[str, Any]) -> Iterator[OrderRequest]:
        """Preferred slice-aware entry point (Lean parity).

        Receives every co-timed bar at once so multi-symbol alphas don't
        re-fire ``rebalance_every`` times per timestamp.
        """
        return iter(self._step(slice_.timestamp, context))

    def on_order_update(self, order: OrderData) -> None:  # pragma: no cover — hook
        logger.debug("[%s] order update: %s %s", self.strategy_id, order.order_id, order.status)
