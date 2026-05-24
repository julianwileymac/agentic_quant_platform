"""Order lifecycle finite state machine.

Canonical FSM (blueprint §G.1):

::

    CREATED -> VALIDATED -> ROUTED -> ACKNOWLEDGED
                                          |
                       +------------------+------------------+
                       v                                     v
                PARTIALLY_FILLED -----> FILLED        CANCEL_PENDING -> CANCELLED

    Any state can transition to REJECTED / EXPIRED / DISPUTED.

Reconciliation conflicts (e.g. venue reports a fill we never issued an
order for) elevate to ``DISPUTED`` and quarantine the strategy from
new entries per blueprint §G.5.

Every transition is **idempotent**: replaying the same transition is
a no-op. Invalid transitions raise :class:`OrderTransitionError`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from aqp_bots.schemas.trading import OrderStatus

logger = logging.getLogger(__name__)


class OrderTransitionError(RuntimeError):
    """Raised on illegal order FSM transition."""


_TERMINAL_STATES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.EXPIRED,
    }
)

_VALID_FORWARD: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset(
        {OrderStatus.VALIDATED, OrderStatus.REJECTED, OrderStatus.DISPUTED}
    ),
    OrderStatus.VALIDATED: frozenset(
        {OrderStatus.ROUTED, OrderStatus.REJECTED, OrderStatus.CANCELLED}
    ),
    OrderStatus.ROUTED: frozenset(
        {
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.REJECTED,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.DISPUTED,
        }
    ),
    OrderStatus.ACKNOWLEDGED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.DISPUTED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_PENDING,
            OrderStatus.CANCELLED,
            OrderStatus.EXPIRED,
            OrderStatus.DISPUTED,
        }
    ),
    OrderStatus.CANCEL_PENDING: frozenset(
        {
            OrderStatus.CANCELLED,
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.DISPUTED,
        }
    ),
    OrderStatus.FILLED: frozenset({OrderStatus.DISPUTED}),
    OrderStatus.CANCELLED: frozenset({OrderStatus.DISPUTED}),
    OrderStatus.REJECTED: frozenset({OrderStatus.DISPUTED}),
    OrderStatus.EXPIRED: frozenset({OrderStatus.DISPUTED}),
    OrderStatus.DISPUTED: frozenset(),
}


@dataclass(slots=True)
class OrderTransition:
    """One state transition.  Captured by :class:`OrderFSM.history`."""

    from_state: OrderStatus
    to_state: OrderStatus
    reason: str
    at_utc: datetime
    fill_qty: Decimal = Decimal("0")
    fill_price: Decimal | None = None
    extras: dict[str, Any] = field(default_factory=dict)


class OrderFSM:
    """One-order lifecycle state machine.

    Usage::

        fsm = OrderFSM(client_order_id="...", quantity=Decimal("100"))
        fsm.transition(OrderStatus.VALIDATED, reason="risk pass")
        fsm.transition(OrderStatus.ROUTED, reason="sent to venue")
        fsm.on_fill(fill_qty=Decimal("60"), fill_price=Decimal("100.5"))
        fsm.on_fill(fill_qty=Decimal("40"), fill_price=Decimal("100.6"))
        assert fsm.state == OrderStatus.FILLED
    """

    def __init__(
        self,
        *,
        client_order_id: str,
        quantity: Decimal,
        initial: OrderStatus = OrderStatus.CREATED,
    ) -> None:
        self.client_order_id = client_order_id
        self.quantity = Decimal(quantity)
        self._state: OrderStatus = initial
        self._cumulative_qty: Decimal = Decimal("0")
        self._avg_fill_price: Decimal | None = None
        self._history: list[OrderTransition] = []
        self._listeners: list[Callable[[OrderTransition], None]] = []

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> OrderStatus:
        return self._state

    @property
    def cumulative_qty(self) -> Decimal:
        return self._cumulative_qty

    @property
    def leaves_qty(self) -> Decimal:
        return self.quantity - self._cumulative_qty

    @property
    def avg_fill_price(self) -> Decimal | None:
        return self._avg_fill_price

    @property
    def history(self) -> tuple[OrderTransition, ...]:
        return tuple(self._history)

    def is_terminal(self) -> bool:
        return self._state in _TERMINAL_STATES or self._state == OrderStatus.DISPUTED

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def subscribe(self, listener: Callable[[OrderTransition], None]) -> None:
        self._listeners.append(listener)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        target: OrderStatus,
        *,
        reason: str = "",
        extras: dict[str, Any] | None = None,
    ) -> OrderTransition:
        """Move to ``target``. Idempotent — replaying a transition is a no-op."""
        if target == self._state:
            return self._history[-1] if self._history else self._record_noop()

        valid = _VALID_FORWARD.get(self._state, frozenset())
        if target not in valid:
            raise OrderTransitionError(
                f"order {self.client_order_id}: illegal transition "
                f"{self._state.value} -> {target.value}; "
                f"valid: {sorted(s.value for s in valid)}"
            )
        evt = OrderTransition(
            from_state=self._state,
            to_state=target,
            reason=reason,
            at_utc=datetime.now(timezone.utc),
            extras=extras or {},
        )
        self._state = target
        self._history.append(evt)
        for listener in self._listeners:
            try:
                listener(evt)
            except Exception:  # noqa: BLE001
                logger.debug("order listener raised", exc_info=True)
        return evt

    def on_fill(self, *, fill_qty: Decimal, fill_price: Decimal) -> OrderTransition:
        """Apply one fill (partial or final). Updates avg + cumulative."""
        if fill_qty <= 0:
            raise OrderTransitionError(
                f"order {self.client_order_id}: fill_qty must be > 0 (got {fill_qty})"
            )
        new_cumulative = self._cumulative_qty + fill_qty
        if new_cumulative > self.quantity:
            # Over-fill — elevate to DISPUTED (venue replay or fat-finger).
            return self.transition(
                OrderStatus.DISPUTED,
                reason=f"over-fill: cumulative {new_cumulative} > quantity {self.quantity}",
            )
        # Volume-weighted average price.
        if self._avg_fill_price is None or self._cumulative_qty == 0:
            self._avg_fill_price = fill_price
        else:
            total_notional = (
                self._avg_fill_price * self._cumulative_qty + fill_price * fill_qty
            )
            self._avg_fill_price = total_notional / new_cumulative
        self._cumulative_qty = new_cumulative

        target = (
            OrderStatus.FILLED
            if new_cumulative == self.quantity
            else OrderStatus.PARTIALLY_FILLED
        )
        evt = self.transition(
            target,
            reason=f"fill qty={fill_qty} price={fill_price}",
            extras={"fill_qty": str(fill_qty), "fill_price": str(fill_price)},
        )
        # Stamp fill details on the transition record.
        evt.fill_qty = fill_qty
        evt.fill_price = fill_price
        return evt

    def cancel_pending(self, *, reason: str = "cancel_requested") -> OrderTransition:
        return self.transition(OrderStatus.CANCEL_PENDING, reason=reason)

    def reject(self, *, reason: str) -> OrderTransition:
        return self.transition(OrderStatus.REJECTED, reason=reason)

    def expire(self, *, reason: str = "session_expired") -> OrderTransition:
        return self.transition(OrderStatus.EXPIRED, reason=reason)

    def dispute(self, *, reason: str) -> OrderTransition:
        """Quarantine the order due to reconciliation conflict."""
        return self.transition(OrderStatus.DISPUTED, reason=reason)

    def _record_noop(self) -> OrderTransition:
        evt = OrderTransition(
            from_state=self._state,
            to_state=self._state,
            reason="noop (already in state)",
            at_utc=datetime.now(timezone.utc),
        )
        self._history.append(evt)
        return evt


__all__ = [
    "OrderFSM",
    "OrderTransition",
    "OrderTransitionError",
]
