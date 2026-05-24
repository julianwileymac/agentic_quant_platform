"""Execution layer: OMS, EMS, SOR, order FSM, idempotency, reconciliation.

Six modules:

- :mod:`aqp_bots.execution.lifecycle` — Order FSM (blueprint §G.1)
- :mod:`aqp_bots.execution.oms` — :class:`OrderManagementSystem`
  tracking working orders + fills
- :mod:`aqp_bots.execution.ems` — :class:`ExecutionManagementSystem`
  with TWAP / VWAP / POV / IS / Iceberg algos
- :mod:`aqp_bots.execution.sor` — :class:`SmartOrderRouter` Protocol
  with the default :class:`LatencyAwareSOR`
- :mod:`aqp_bots.execution.idempotency` — UUIDv7 + content-hash LRU
- :mod:`aqp_bots.execution.reconcile` — drop-copy + ``OrderMassStatusRequest``
"""
from __future__ import annotations

from aqp_bots.execution.ems import (
    ExecutionAlgorithm,
    ExecutionManagementSystem,
    IcebergAlgo,
    ISAlgo,
    POVAlgo,
    TWAPAlgo,
    VWAPAlgo,
)
from aqp_bots.execution.idempotency import IdempotencyCache
from aqp_bots.execution.lifecycle import (
    OrderFSM,
    OrderTransitionError,
)
from aqp_bots.execution.oms import OrderManagementSystem
from aqp_bots.execution.reconcile import Reconciler, ReconcileResult
from aqp_bots.execution.sor import (
    LatencyAwareSOR,
    RoundRobinSOR,
    SmartOrderRouter,
    VenueScore,
)

__all__ = [
    "ExecutionAlgorithm",
    "ExecutionManagementSystem",
    "ISAlgo",
    "IcebergAlgo",
    "IdempotencyCache",
    "LatencyAwareSOR",
    "OrderFSM",
    "OrderManagementSystem",
    "OrderTransitionError",
    "POVAlgo",
    "ReconcileResult",
    "Reconciler",
    "RoundRobinSOR",
    "SmartOrderRouter",
    "TWAPAlgo",
    "VWAPAlgo",
    "VenueScore",
]
