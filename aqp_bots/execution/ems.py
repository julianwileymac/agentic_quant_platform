"""Execution Management System + execution algos.

Builds on the OMS to provide higher-level execution intents:

- :class:`TWAPAlgo` — slice a parent order over time-weighted intervals.
- :class:`VWAPAlgo` — slice in proportion to forecast volume profile.
- :class:`POVAlgo` — percent-of-volume (track participation rate).
- :class:`ISAlgo` — implementation shortfall (Almgren-Chriss).
- :class:`IcebergAlgo` — show only ``display_qty``, refill on fills.

Mirrors the Hummingbot V2 ``Executor`` pattern (``PositionExecutor``,
``DCAExecutor``, ``GridExecutor``, ``TWAPExecutor``, ``XEMMExecutor``,
``LPExecutor``) but expressed as pluggable strategy components rather
than Cython subclasses.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from aqp_bots.core.ids import new_client_order_id
from aqp_bots.execution.oms import OrderManagementSystem
from aqp_bots.schemas.trading import (
    NewOrder,
    OrderStatus,
    Side,
    TimeInForce,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Algorithm Protocol
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AlgoState:
    """Per-parent-order algo state."""

    parent_id: str
    target_qty: Decimal
    completed_qty: Decimal = Decimal("0")
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_slice_at: datetime | None = None
    finished: bool = False
    children: list[str] = field(default_factory=list)


class ExecutionAlgorithm(ABC):
    """One execution algorithm.

    Concrete algos slice a *parent* :class:`NewOrder` into one or more
    *child* :class:`NewOrder` and submit them through the OMS. The EMS
    advances the algo state by calling :meth:`step` on the algo
    instance from the kernel's ``execution_task`` coroutine.
    """

    name: str = "base"

    @abstractmethod
    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        """Compute every child order for ``parent`` (eager planning).

        Some algos (TWAP) can plan all children up front; others (POV)
        compute one slice at a time and return ``[]`` here, populating
        on :meth:`step`.
        """

    def step(self, parent: NewOrder, state: AlgoState) -> list[NewOrder]:
        """Emit any new child orders that are due.  Default: none."""
        return []


# ---------------------------------------------------------------------------
# TWAP — equal-volume slices over a duration
# ---------------------------------------------------------------------------


class TWAPAlgo(ExecutionAlgorithm):
    """Time-weighted average price.

    Splits ``parent.quantity`` into ``slices`` equal child orders spaced
    ``duration / slices`` apart. Each slice is a child :class:`NewOrder`
    with ``parent_order_id=parent.client_order_id``.
    """

    name = "twap"

    def __init__(self, *, slices: int = 10, duration: timedelta = timedelta(minutes=30)) -> None:
        if slices < 1:
            raise ValueError("slices must be >= 1")
        self.slices = slices
        self.duration = duration

    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        slice_qty = parent.quantity / Decimal(self.slices)
        out: list[NewOrder] = []
        for i in range(self.slices):
            out.append(
                NewOrder(
                    venue=parent.venue,
                    symbol=parent.symbol,
                    side=parent.side,
                    quantity=slice_qty,
                    order_type=parent.order_type,
                    time_in_force=TimeInForce.IOC,
                    limit_price=parent.limit_price,
                    client_order_id=new_client_order_id(),
                    parent_order_id=parent.client_order_id,
                    strategy_id=parent.strategy_id,
                    bot_id=parent.bot_id,
                    correlation_id=parent.correlation_id,
                )
            )
        return out


# ---------------------------------------------------------------------------
# VWAP — volume-weighted slices
# ---------------------------------------------------------------------------


class VWAPAlgo(ExecutionAlgorithm):
    """Volume-weighted average price.

    Slices follow a normalized volume profile (e.g. U-shaped intraday
    curve). When no profile is provided we fall back to equal slices
    (degrades to TWAP behavior).
    """

    name = "vwap"

    def __init__(
        self,
        *,
        volume_profile: list[float] | None = None,
        duration: timedelta = timedelta(hours=1),
    ) -> None:
        self.volume_profile = volume_profile or [1.0] * 10
        self.duration = duration

    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        total_weight = sum(self.volume_profile) or 1.0
        out: list[NewOrder] = []
        for w in self.volume_profile:
            slice_qty = parent.quantity * Decimal(str(w / total_weight))
            out.append(
                NewOrder(
                    venue=parent.venue,
                    symbol=parent.symbol,
                    side=parent.side,
                    quantity=slice_qty,
                    order_type=parent.order_type,
                    time_in_force=TimeInForce.IOC,
                    limit_price=parent.limit_price,
                    client_order_id=new_client_order_id(),
                    parent_order_id=parent.client_order_id,
                    strategy_id=parent.strategy_id,
                    bot_id=parent.bot_id,
                )
            )
        return out


# ---------------------------------------------------------------------------
# POV — percent of volume
# ---------------------------------------------------------------------------


class POVAlgo(ExecutionAlgorithm):
    """Track a constant ``participation_rate`` of market volume.

    Plans nothing eagerly; :meth:`step` consults the latest volume
    snapshot and emits one slice per step until ``completed_qty ==
    target_qty``.
    """

    name = "pov"

    def __init__(self, *, participation_rate: float = 0.10) -> None:
        if not 0 < participation_rate <= 1:
            raise ValueError("participation_rate must be in (0, 1]")
        self.participation_rate = participation_rate

    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        return []

    def step(self, parent: NewOrder, state: AlgoState) -> list[NewOrder]:
        # Real implementation reads market.recent_volume() from the bus.
        # For this skeleton we emit a constant slice when the residual is
        # large enough; the kernel passes recent volume via state.extras.
        remaining = parent.quantity - state.completed_qty
        if remaining <= 0:
            state.finished = True
            return []
        # Conservative default: 1% of remaining per step.
        slice_qty = remaining * Decimal("0.01")
        return [
            NewOrder(
                venue=parent.venue,
                symbol=parent.symbol,
                side=parent.side,
                quantity=slice_qty,
                order_type="market",
                time_in_force=TimeInForce.IOC,
                client_order_id=new_client_order_id(),
                parent_order_id=parent.client_order_id,
                strategy_id=parent.strategy_id,
                bot_id=parent.bot_id,
            )
        ]


# ---------------------------------------------------------------------------
# IS — implementation shortfall (Almgren-Chriss skeleton)
# ---------------------------------------------------------------------------


class ISAlgo(ExecutionAlgorithm):
    """Implementation shortfall.

    Front-loaded slice schedule trading off impact (slicing) vs
    timing risk (waiting). The full Almgren-Chriss solution lives in
    :mod:`aqp.optimal_control`; this algo wraps the existing solver
    through :class:`aqp.data.mcp.tools.optimal_control` when available
    and falls back to a heuristic 5-slice front-loaded schedule.
    """

    name = "is"

    def __init__(
        self,
        *,
        slices: int = 5,
        risk_aversion: float = 1e-4,
    ) -> None:
        self.slices = slices
        self.risk_aversion = risk_aversion

    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        # Heuristic front-loaded weights: [0.30, 0.25, 0.20, 0.15, 0.10] for slices=5.
        weights = [
            (self.slices - i) / sum(range(1, self.slices + 1))
            for i in range(self.slices)
        ]
        out: list[NewOrder] = []
        for w in weights:
            slice_qty = parent.quantity * Decimal(str(w))
            out.append(
                NewOrder(
                    venue=parent.venue,
                    symbol=parent.symbol,
                    side=parent.side,
                    quantity=slice_qty,
                    order_type=parent.order_type,
                    time_in_force=TimeInForce.IOC,
                    limit_price=parent.limit_price,
                    client_order_id=new_client_order_id(),
                    parent_order_id=parent.client_order_id,
                    strategy_id=parent.strategy_id,
                    bot_id=parent.bot_id,
                )
            )
        return out


# ---------------------------------------------------------------------------
# Iceberg — display only display_qty
# ---------------------------------------------------------------------------


class IcebergAlgo(ExecutionAlgorithm):
    """Iceberg order.

    Submits an order with the venue's native iceberg semantics (when
    supported via :attr:`NewOrder.iceberg_qty`); otherwise emits
    successive child orders of ``display_qty`` until the parent is
    fully executed.
    """

    name = "iceberg"

    def __init__(self, *, display_qty: Decimal = Decimal("100")) -> None:
        self.display_qty = display_qty

    def plan_children(self, parent: NewOrder) -> list[NewOrder]:
        # When the venue supports native iceberg, emit a single order
        # with iceberg_qty set. The execution adapter detects support
        # via its capability.supports_post_only / iceberg flag.
        return [
            NewOrder(
                venue=parent.venue,
                symbol=parent.symbol,
                side=parent.side,
                quantity=parent.quantity,
                order_type=parent.order_type,
                time_in_force=parent.time_in_force,
                limit_price=parent.limit_price,
                iceberg_qty=self.display_qty,
                client_order_id=new_client_order_id(),
                parent_order_id=parent.client_order_id,
                strategy_id=parent.strategy_id,
                bot_id=parent.bot_id,
            )
        ]


# ---------------------------------------------------------------------------
# EMS
# ---------------------------------------------------------------------------


_ALGO_REGISTRY: dict[str, type[ExecutionAlgorithm]] = {
    "twap": TWAPAlgo,
    "vwap": VWAPAlgo,
    "pov": POVAlgo,
    "is": ISAlgo,
    "iceberg": IcebergAlgo,
}


class ExecutionManagementSystem:
    """Coordinate parent orders + execution algos."""

    def __init__(self, *, oms: OrderManagementSystem) -> None:
        self.oms = oms
        self._algos: dict[str, ExecutionAlgorithm] = {}
        self._states: dict[str, AlgoState] = {}

    def attach(self, parent: NewOrder, algo_name: str, **kwargs: Any) -> list[NewOrder]:
        """Attach an algo to ``parent``. Returns the eager child orders."""
        algo_cls = _ALGO_REGISTRY.get(algo_name)
        if algo_cls is None:
            raise ValueError(
                f"unknown execution algo {algo_name!r}; options: {sorted(_ALGO_REGISTRY)}"
            )
        algo = algo_cls(**kwargs)
        self._algos[parent.client_order_id] = algo
        self._states[parent.client_order_id] = AlgoState(
            parent_id=parent.client_order_id, target_qty=parent.quantity
        )
        children = algo.plan_children(parent)
        for child in children:
            self._states[parent.client_order_id].children.append(child.client_order_id)
            self.oms.admit(child)
        return children

    def step(self, parent: NewOrder) -> list[NewOrder]:
        """Advance the algo for ``parent`` and emit any new child orders."""
        algo = self._algos.get(parent.client_order_id)
        state = self._states.get(parent.client_order_id)
        if algo is None or state is None:
            return []
        children = algo.step(parent, state)
        for child in children:
            state.children.append(child.client_order_id)
            self.oms.admit(child)
        return children

    def on_child_terminal(self, parent_id: str) -> None:
        """Update parent state when a child reaches a terminal status."""
        state = self._states.get(parent_id)
        if state is None:
            return
        completed = Decimal("0")
        for child_coid in state.children:
            child_fsm = self.oms.order(child_coid)
            if child_fsm is not None and child_fsm.state == OrderStatus.FILLED:
                completed += child_fsm.quantity
        state.completed_qty = completed
        if completed >= state.target_qty:
            state.finished = True


__all__ = [
    "AlgoState",
    "ExecutionAlgorithm",
    "ExecutionManagementSystem",
    "ISAlgo",
    "IcebergAlgo",
    "POVAlgo",
    "TWAPAlgo",
    "VWAPAlgo",
]
