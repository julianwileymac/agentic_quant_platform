"""Phase 4: Order lifecycle FSM."""
from __future__ import annotations

from decimal import Decimal

import pytest

from aqp_bots.execution.lifecycle import OrderFSM, OrderTransitionError
from aqp_bots.schemas.trading import OrderStatus


def _new_order(qty: str = "100") -> OrderFSM:
    return OrderFSM(client_order_id="coid-test", quantity=Decimal(qty))


def test_initial_state_is_created() -> None:
    fsm = _new_order()
    assert fsm.state == OrderStatus.CREATED
    assert fsm.cumulative_qty == Decimal("0")
    assert not fsm.is_terminal()


def test_happy_path_created_to_filled() -> None:
    fsm = _new_order("100")
    fsm.transition(OrderStatus.VALIDATED, reason="risk pass")
    fsm.transition(OrderStatus.ROUTED, reason="sent")
    fsm.transition(OrderStatus.ACKNOWLEDGED, reason="venue ack")
    fsm.on_fill(fill_qty=Decimal("60"), fill_price=Decimal("100.50"))
    assert fsm.state == OrderStatus.PARTIALLY_FILLED
    assert fsm.cumulative_qty == Decimal("60")
    fsm.on_fill(fill_qty=Decimal("40"), fill_price=Decimal("100.55"))
    assert fsm.state == OrderStatus.FILLED
    assert fsm.cumulative_qty == Decimal("100")
    assert fsm.leaves_qty == Decimal("0")
    assert fsm.is_terminal()


def test_avg_price_is_volume_weighted() -> None:
    fsm = _new_order("100")
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.ROUTED)
    fsm.transition(OrderStatus.ACKNOWLEDGED)
    fsm.on_fill(fill_qty=Decimal("50"), fill_price=Decimal("100"))
    fsm.on_fill(fill_qty=Decimal("50"), fill_price=Decimal("110"))
    # VWAP = (50*100 + 50*110) / 100 = 105
    assert fsm.avg_fill_price == Decimal("105")


def test_cancel_path() -> None:
    fsm = _new_order()
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.ROUTED)
    fsm.transition(OrderStatus.ACKNOWLEDGED)
    fsm.cancel_pending()
    assert fsm.state == OrderStatus.CANCEL_PENDING
    fsm.transition(OrderStatus.CANCELLED, reason="venue cancel ack")
    assert fsm.is_terminal()


def test_reject_path() -> None:
    fsm = _new_order()
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.ROUTED)
    fsm.reject(reason="margin")
    assert fsm.state == OrderStatus.REJECTED
    assert fsm.is_terminal()


def test_over_fill_disputes_order() -> None:
    fsm = _new_order("100")
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.ROUTED)
    fsm.transition(OrderStatus.ACKNOWLEDGED)
    fsm.on_fill(fill_qty=Decimal("80"), fill_price=Decimal("100"))
    fsm.on_fill(fill_qty=Decimal("50"), fill_price=Decimal("100"))
    # 80 + 50 > 100 -> DISPUTED
    assert fsm.state == OrderStatus.DISPUTED


def test_idempotent_replay_is_noop() -> None:
    fsm = _new_order()
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.VALIDATED)  # replay
    # State is unchanged; history records the noop.
    assert fsm.state == OrderStatus.VALIDATED


def test_illegal_transition_raises() -> None:
    fsm = _new_order()
    with pytest.raises(OrderTransitionError):
        fsm.transition(OrderStatus.FILLED)


def test_negative_fill_raises() -> None:
    fsm = _new_order()
    fsm.transition(OrderStatus.VALIDATED)
    fsm.transition(OrderStatus.ROUTED)
    fsm.transition(OrderStatus.ACKNOWLEDGED)
    with pytest.raises(OrderTransitionError):
        fsm.on_fill(fill_qty=Decimal("-10"), fill_price=Decimal("100"))
