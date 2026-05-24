"""Order Management System.

Tracks the live state of every order the bot has submitted. Composes
the :class:`OrderFSM` from :mod:`aqp_bots.execution.lifecycle` with the
:class:`IdempotencyCache` from :mod:`aqp_bots.execution.idempotency`.

Persisted via :class:`aqp_bots.state.store.EventStore`; this in-memory
OMS is rebuilt from the latest snapshot + event replay on bot restart.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from aqp_bots.execution.idempotency import IdempotencyCache, order_content_hash
from aqp_bots.execution.lifecycle import OrderFSM, OrderTransitionError
from aqp_bots.schemas.trading import (
    Fill,
    NewOrder,
    OrderAck,
    OrderRef,
    OrderStatus,
    Position,
    Reject,
)

logger = logging.getLogger(__name__)


class OrderManagementSystem:
    """In-bot order book.

    Stores one :class:`OrderFSM` per active ``client_order_id`` and
    derives positions / leaves / cumulative qty from the fill stream.
    """

    def __init__(self, *, idempotency_lru_size: int = 4096) -> None:
        self._fsms: dict[str, OrderFSM] = {}
        self._idempotency = IdempotencyCache(size=idempotency_lru_size)
        self._positions: dict[str, Position] = {}  # keyed by (venue, symbol)

    # ------------------------------------------------------------------
    # Order intake
    # ------------------------------------------------------------------

    def admit(self, order: NewOrder) -> tuple[OrderFSM, bool]:
        """Admit a new order. Returns ``(fsm, is_new)``.

        Idempotent: a retry with the same logical content returns the
        original FSM and ``is_new=False``.
        """
        content_hash = order_content_hash(order)
        existing_coid = self._idempotency.get(content_hash)
        if existing_coid and existing_coid in self._fsms:
            return self._fsms[existing_coid], False

        fsm = OrderFSM(
            client_order_id=order.client_order_id, quantity=order.quantity
        )
        self._fsms[order.client_order_id] = fsm
        self._idempotency.put(content_hash, order.client_order_id)
        return fsm, True

    # ------------------------------------------------------------------
    # State update from venue
    # ------------------------------------------------------------------

    def on_ack(self, ack: OrderAck) -> None:
        fsm = self._fsms.get(ack.ref.client_order_id)
        if fsm is None:
            logger.debug("ack for unknown order %s", ack.ref.client_order_id)
            return
        try:
            if fsm.state == OrderStatus.CREATED:
                fsm.transition(OrderStatus.VALIDATED, reason="local validate")
            if fsm.state == OrderStatus.VALIDATED:
                fsm.transition(OrderStatus.ROUTED, reason="sent to venue")
            if fsm.state == OrderStatus.ROUTED:
                fsm.transition(OrderStatus.ACKNOWLEDGED, reason="venue ack")
        except OrderTransitionError:
            logger.debug("ack ignored — order in terminal state", exc_info=True)

    def on_fill(self, fill: Fill) -> None:
        fsm = self._fsms.get(fill.ref.client_order_id)
        if fsm is None:
            logger.warning("fill for unknown order %s", fill.ref.client_order_id)
            return
        try:
            fsm.on_fill(fill_qty=fill.fill_qty, fill_price=fill.fill_price)
            self._update_position(fill)
        except OrderTransitionError:
            logger.exception("on_fill transition failed")

    def on_reject(self, rej: Reject) -> None:
        fsm = self._fsms.get(rej.ref.client_order_id)
        if fsm is None:
            return
        try:
            fsm.reject(reason=f"{rej.reason_code}: {rej.reason_text}")
        except OrderTransitionError:
            pass

    def on_cancel_ack(self, ref: OrderRef) -> None:
        fsm = self._fsms.get(ref.client_order_id)
        if fsm is None:
            return
        try:
            fsm.transition(OrderStatus.CANCELLED, reason="venue cancel ack")
        except OrderTransitionError:
            pass

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def working_orders(self) -> Iterator[OrderFSM]:
        for fsm in self._fsms.values():
            if not fsm.is_terminal():
                yield fsm

    def order(self, client_order_id: str) -> OrderFSM | None:
        return self._fsms.get(client_order_id)

    def positions(self) -> tuple[Position, ...]:
        return tuple(self._positions.values())

    def position(self, venue: str, symbol: str) -> Position | None:
        return self._positions.get(f"{venue}:{symbol}")

    # ------------------------------------------------------------------
    # Internal: position aggregation
    # ------------------------------------------------------------------

    def _update_position(self, fill: Fill) -> None:
        key = f"{fill.ref.venue}:{fill.ref.symbol}"
        from decimal import Decimal

        pos = self._positions.get(key)
        signed_qty = fill.fill_qty if fill.side == "buy" else -fill.fill_qty
        if pos is None:
            self._positions[key] = Position(
                venue=fill.ref.venue,
                symbol=fill.ref.symbol,
                qty=signed_qty,
                avg_price=fill.fill_price,
                last_update_ns=fill.processed_ts_ns or fill.ingress_ts_ns,
            )
            return
        new_qty = pos.qty + signed_qty
        # New volume-weighted average when increasing exposure on the same side;
        # leave avg unchanged when reducing.
        if (pos.qty >= 0 and signed_qty > 0) or (pos.qty <= 0 and signed_qty < 0):
            total_abs = abs(pos.qty) + abs(signed_qty)
            new_avg = (
                (pos.avg_price * abs(pos.qty) + fill.fill_price * abs(signed_qty))
                / total_abs
                if total_abs > 0
                else fill.fill_price
            )
        else:
            new_avg = pos.avg_price
        self._positions[key] = Position(
            venue=pos.venue,
            symbol=pos.symbol,
            qty=new_qty,
            avg_price=new_avg,
            realized_pnl=pos.realized_pnl,
            unrealized_pnl=pos.unrealized_pnl,
            last_update_ns=fill.processed_ts_ns or fill.ingress_ts_ns,
        )


__all__ = ["OrderManagementSystem"]
