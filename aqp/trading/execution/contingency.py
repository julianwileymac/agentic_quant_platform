"""Contingency-graph state machine (OCO / OUO / OTO).

Walks every open :class:`OrderList` and emits cancel / amend / activate
commands when execution reports arrive that should trigger a contingent
action. Useful when the underlying venue does NOT support an atomic
OCO submission and the platform has to simulate the relationships.

Three relationships:

* **OCO** (one-cancels-other) -- when any constituent is filled
  (partially or fully), the others are canceled.
* **OUO** (one-updates-other) -- when any constituent's quantity
  changes (partial fill or amend), every other constituent's quantity
  is updated to match the remaining size.
* **OTO** (one-triggers-other) -- the parent is the trigger; children
  are emulated until the parent fills, then they're submitted.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aqp.core.domain.enums import ContingencyType, OrderStatus
from aqp.core.domain.identifiers import ClientOrderId, OrderListId
from aqp.core.domain.orders import DomainOrder, OrderList

logger = logging.getLogger(__name__)


class ContingencyAction(StrEnum):
    """A command the contingency manager wants the broker to execute."""

    CANCEL = "cancel"
    UPDATE_QUANTITY = "update_quantity"
    SUBMIT = "submit"


@dataclass(slots=True)
class ContingencyCommand:
    """Single command emitted by the contingency manager."""

    action: ContingencyAction
    target_order_id: ClientOrderId
    new_quantity: Decimal | None = None
    reason: str = ""


@dataclass
class ContingencyState:
    """Per-order-list state tracked by the manager."""

    order_list: OrderList
    status: str = "active"  # active | partially_executed | fully_executed | canceled
    ts_last: datetime = field(default_factory=datetime.utcnow)
    children_activated: bool = False  # OTO only
    # Per-order shadow of remaining quantity (so OUO can compute deltas
    # without re-fetching from the venue).
    remaining_quantity: dict[ClientOrderId, Decimal] = field(default_factory=dict)


class ContingencyManager:
    """In-memory state machine for OCO / OUO / OTO order lists.

    Designed to be embedded in the paper session loop or the live
    execution dispatcher: feed it open lists via :meth:`register` and
    every incoming execution report via :meth:`on_execution_report`.
    The manager returns a list of :class:`ContingencyCommand` objects
    the caller dispatches to the broker.

    Thread safety: the manager mutates per-list state; callers MUST
    serialise calls (the paper session does this naturally via its
    single-threaded bar loop).
    """

    def __init__(self) -> None:
        self._lists: dict[OrderListId, ContingencyState] = {}
        # Reverse index: which order list does an order belong to?
        self._order_to_list: dict[ClientOrderId, OrderListId] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, order_list: OrderList) -> ContingencyState:
        """Track ``order_list``; subsequent execution reports route here."""
        state = ContingencyState(
            order_list=order_list,
            remaining_quantity={
                o.client_order_id: o.remaining_quantity for o in order_list.orders
            },
        )
        self._lists[order_list.order_list_id] = state
        for o in order_list.orders:
            self._order_to_list[o.client_order_id] = order_list.order_list_id
        return state

    def unregister(self, order_list_id: OrderListId) -> None:
        """Remove ``order_list_id`` (called when fully executed or canceled)."""
        state = self._lists.pop(order_list_id, None)
        if state is None:
            return
        for o in state.order_list.orders:
            self._order_to_list.pop(o.client_order_id, None)

    @property
    def active_lists(self) -> list[OrderList]:
        return [s.order_list for s in self._lists.values() if s.status == "active"]

    # ------------------------------------------------------------------
    # Event ingestion
    # ------------------------------------------------------------------

    def on_execution_report(
        self,
        *,
        client_order_id: ClientOrderId,
        order_status: OrderStatus,
        cumulative_quantity: Decimal | None = None,
        last_quantity: Decimal | None = None,
    ) -> list[ContingencyCommand]:
        """Emit commands when an execution report changes a list's state.

        Returns a list of :class:`ContingencyCommand` objects in the
        order they should be dispatched. An empty list means no
        cross-order action is needed.
        """
        list_id = self._order_to_list.get(client_order_id)
        if list_id is None:
            return []
        state = self._lists.get(list_id)
        if state is None or state.status != "active":
            return []

        commands: list[ContingencyCommand] = []
        contingency = state.order_list.contingency_type

        if contingency == ContingencyType.OCO:
            commands.extend(
                self._handle_oco(state, client_order_id, order_status)
            )
        elif contingency == ContingencyType.OUO:
            commands.extend(
                self._handle_ouo(
                    state,
                    client_order_id,
                    order_status,
                    cumulative_quantity=cumulative_quantity,
                )
            )
        elif contingency == ContingencyType.OTO:
            commands.extend(
                self._handle_oto(state, client_order_id, order_status)
            )

        state.ts_last = datetime.utcnow()
        return commands

    # ------------------------------------------------------------------
    # Per-contingency handlers
    # ------------------------------------------------------------------

    def _handle_oco(
        self,
        state: ContingencyState,
        client_order_id: ClientOrderId,
        order_status: OrderStatus,
    ) -> list[ContingencyCommand]:
        """OCO: any fill (full or partial) cancels every other constituent.

        Implementation note: we cancel on PARTIALLY_FILLED so the OCO
        invariant holds even when only part of one leg fills before a
        cancel command lands at the venue. Cleanups for already-filled
        peers are no-ops at the venue level.
        """
        if order_status not in {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED}:
            return []

        commands: list[ContingencyCommand] = []
        for order in state.order_list.orders:
            if order.client_order_id == client_order_id:
                continue
            if order.is_terminal:
                continue
            commands.append(
                ContingencyCommand(
                    action=ContingencyAction.CANCEL,
                    target_order_id=order.client_order_id,
                    reason=f"OCO: {client_order_id} filled, canceling peer",
                )
            )
        if order_status == OrderStatus.FILLED:
            state.status = "fully_executed"
        else:
            state.status = "partially_executed"
        return commands

    def _handle_ouo(
        self,
        state: ContingencyState,
        client_order_id: ClientOrderId,
        order_status: OrderStatus,
        *,
        cumulative_quantity: Decimal | None,
    ) -> list[ContingencyCommand]:
        """OUO: when one leg's remaining qty drops, update every peer to match."""
        if cumulative_quantity is None:
            return []
        # Find the order whose execution report we just received.
        target_order: DomainOrder | None = None
        for order in state.order_list.orders:
            if order.client_order_id == client_order_id:
                target_order = order
                break
        if target_order is None:
            return []
        new_remaining = max(
            Decimal("0"), target_order.quantity - cumulative_quantity
        )
        prev_remaining = state.remaining_quantity.get(
            client_order_id, target_order.remaining_quantity
        )
        if new_remaining == prev_remaining:
            return []
        state.remaining_quantity[client_order_id] = new_remaining

        commands: list[ContingencyCommand] = []
        if new_remaining == 0:
            # Fully filled -> cancel the other leg (degenerate to OCO).
            for order in state.order_list.orders:
                if order.client_order_id == client_order_id:
                    continue
                commands.append(
                    ContingencyCommand(
                        action=ContingencyAction.CANCEL,
                        target_order_id=order.client_order_id,
                        reason="OUO: peer fully filled",
                    )
                )
            state.status = "fully_executed"
        else:
            # Partial fill -> shrink the peer's remaining qty to match.
            for order in state.order_list.orders:
                if order.client_order_id == client_order_id:
                    continue
                commands.append(
                    ContingencyCommand(
                        action=ContingencyAction.UPDATE_QUANTITY,
                        target_order_id=order.client_order_id,
                        new_quantity=new_remaining,
                        reason="OUO: peer quantity updated to match",
                    )
                )
            state.status = "partially_executed"
        return commands

    def _handle_oto(
        self,
        state: ContingencyState,
        client_order_id: ClientOrderId,
        order_status: OrderStatus,
    ) -> list[ContingencyCommand]:
        """OTO: when the parent fills, submit every child."""
        if state.children_activated:
            return []
        parent = state.order_list.parent_order_id
        if parent is None:
            return []
        if client_order_id != parent:
            return []
        if order_status != OrderStatus.FILLED:
            return []
        commands: list[ContingencyCommand] = []
        for order in state.order_list.orders:
            if order.client_order_id == parent:
                continue
            commands.append(
                ContingencyCommand(
                    action=ContingencyAction.SUBMIT,
                    target_order_id=order.client_order_id,
                    reason=f"OTO: parent {parent} filled, releasing child",
                )
            )
        state.children_activated = True
        return commands


__all__ = [
    "ContingencyAction",
    "ContingencyCommand",
    "ContingencyManager",
    "ContingencyState",
]
