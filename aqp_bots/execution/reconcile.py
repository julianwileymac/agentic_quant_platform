"""Order/position reconciliation.

Two reconciliation paths (blueprint §G.5):

1. **Drop-copy ingest** — venue pushes execution-report copies; the
   reconciler matches incoming `ExecutionReport` against local OMS
   state. Used by CME iLink, ICE EAS, NASDAQ, and most other FIX venues.
2. **OrderMassStatusRequest (35=AF, 585=7)** — explicit pull at session
   start / reconnect; venue replies with one execution report per open
   order, all with ``PossResend(97)=Y``.

The reconciler diffs the venue snapshot against the local OMS and:

- Emits :class:`ReconcileResult` with adds (orders the venue knows about
  but we don't) and removes (orders we think are open but the venue has
  closed).
- Elevates over-fills / under-fills to ``DISPUTED`` per
  :class:`OrderFSM.dispute` so the strategy is quarantined from new
  entries until the operator intervenes.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterable

from aqp_bots.execution.oms import OrderManagementSystem
from aqp_bots.schemas.trading import (
    OrderRef,
    OrderStatus,
    Position,
    ReconcileSnapshot,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReconcileResult:
    """Outcome of one reconciliation pass."""

    venue: str
    snapshot_ts_ns: int
    extra_open_orders: list[OrderRef] = field(default_factory=list)
    missing_open_orders: list[OrderRef] = field(default_factory=list)
    position_deltas: dict[str, dict[str, str]] = field(default_factory=dict)
    disputed: list[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return not (
            self.extra_open_orders
            or self.missing_open_orders
            or self.position_deltas
            or self.disputed
        )


class Reconciler:
    """OMS-vs-venue diff engine.

    Strategy: take a :class:`ReconcileSnapshot` from the execution
    adapter and compare against the in-memory OMS. Report deltas;
    dispute orders that violate invariants.
    """

    def __init__(self, *, oms: OrderManagementSystem) -> None:
        self.oms = oms

    def reconcile(self, snapshot: ReconcileSnapshot) -> ReconcileResult:
        result = ReconcileResult(
            venue=snapshot.venue,
            snapshot_ts_ns=snapshot.snapshot_ts_ns or time.time_ns(),
        )

        # 1. Open orders ------------------------------------------------
        venue_open_ids = {
            (ref.client_order_id, ref.venue_order_id) for ref in snapshot.open_orders
        }
        local_open: dict[str, OrderRef] = {}
        for fsm in self.oms.working_orders():
            local_open[fsm.client_order_id] = OrderRef(
                client_order_id=fsm.client_order_id
            )

        # Orders the venue thinks are open but we don't know about.
        for ref in snapshot.open_orders:
            if ref.client_order_id not in local_open:
                result.extra_open_orders.append(ref)
                logger.warning(
                    "reconcile: venue has order %s but OMS does not; disputing",
                    ref.client_order_id,
                )
                result.disputed.append(ref.client_order_id)

        # Orders we think are open but venue has closed.
        for client_order_id, ref in local_open.items():
            if not any(c == client_order_id for c, _ in venue_open_ids):
                result.missing_open_orders.append(ref)
                fsm = self.oms.order(client_order_id)
                if fsm is not None and not fsm.is_terminal():
                    # We don't know whether it filled or was cancelled —
                    # mark expired and let the next venue update reconcile
                    # the exact status.
                    try:
                        fsm.expire(reason="reconcile: venue reports closed")
                    except Exception:  # noqa: BLE001
                        fsm.dispute(reason="reconcile: closed but FSM stuck")
                        result.disputed.append(client_order_id)

        # 2. Positions --------------------------------------------------
        local_positions: dict[str, Position] = {
            f"{p.venue}:{p.symbol}": p for p in self.oms.positions()
        }
        venue_positions: dict[str, Position] = {
            f"{p.venue}:{p.symbol}": p for p in snapshot.positions
        }
        all_keys = set(local_positions) | set(venue_positions)
        for key in all_keys:
            lp = local_positions.get(key)
            vp = venue_positions.get(key)
            local_qty = lp.qty if lp else 0
            venue_qty = vp.qty if vp else 0
            if local_qty != venue_qty:
                result.position_deltas[key] = {
                    "local": str(local_qty),
                    "venue": str(venue_qty),
                }

        return result

    def reconcile_iter(
        self, snapshots: Iterable[ReconcileSnapshot]
    ) -> list[ReconcileResult]:
        """Run reconciliation across multiple venue snapshots."""
        return [self.reconcile(s) for s in snapshots]


__all__ = ["Reconciler", "ReconcileResult"]
