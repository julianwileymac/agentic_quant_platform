"""Tests for the Phase 2 contingency-graph state machine."""
from __future__ import annotations

from decimal import Decimal

from aqp.core.domain.enums import (
    ContingencyType,
    OrderSide,
    OrderStatus,
    OrderType,
)
from aqp.core.domain.identifiers import (
    ClientOrderId,
    InstrumentId,
    OrderListId,
    Symbol2,
    Venue,
)
from aqp.core.domain.orders import (
    LimitOrder,
    OrderList,
    StopMarketOrder,
)
from aqp.trading.execution.contingency import (
    ContingencyAction,
    ContingencyManager,
)


def _iid(sym: str = "AAPL") -> InstrumentId:
    return InstrumentId(Symbol2(sym), Venue("NASDAQ"))


def _take_profit() -> LimitOrder:
    return LimitOrder(
        client_order_id=ClientOrderId("tp-1"),
        instrument_id=_iid(),
        order_side=OrderSide.SELL,
        quantity=Decimal("10"),
        order_type=OrderType.LIMIT,
        price=Decimal("200"),
    )


def _stop_loss() -> StopMarketOrder:
    return StopMarketOrder(
        client_order_id=ClientOrderId("sl-1"),
        instrument_id=_iid(),
        order_side=OrderSide.SELL,
        quantity=Decimal("10"),
        order_type=OrderType.STOP_MARKET,
        trigger_price=Decimal("180"),
    )


def _entry() -> LimitOrder:
    return LimitOrder(
        client_order_id=ClientOrderId("entry-1"),
        instrument_id=_iid(),
        order_side=OrderSide.BUY,
        quantity=Decimal("10"),
        order_type=OrderType.LIMIT,
        price=Decimal("190"),
    )


# ---------------------------------------------------------------------------
# OCO -- one cancels other
# ---------------------------------------------------------------------------


def test_oco_fill_cancels_peer():
    """OCO: when take-profit fills, stop-loss is canceled."""
    mgr = ContingencyManager()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("oco-1"),
            orders=[tp, sl],
            contingency_type=ContingencyType.OCO,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.FILLED,
    )
    assert len(commands) == 1
    assert commands[0].action is ContingencyAction.CANCEL
    assert commands[0].target_order_id.value == "sl-1"


def test_oco_partial_fill_also_cancels_peer():
    """OCO holds even on partial fills -- partial-fill on TP cancels SL."""
    mgr = ContingencyManager()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("oco-2"),
            orders=[tp, sl],
            contingency_type=ContingencyType.OCO,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.PARTIALLY_FILLED,
        cumulative_quantity=Decimal("4"),
    )
    assert len(commands) == 1
    assert commands[0].action is ContingencyAction.CANCEL


def test_oco_unrelated_event_emits_nothing():
    """ACCEPTED / SUBMITTING events don't trigger OCO cancels."""
    mgr = ContingencyManager()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("oco-3"),
            orders=[tp, sl],
            contingency_type=ContingencyType.OCO,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.ACCEPTED,
    )
    assert commands == []


# ---------------------------------------------------------------------------
# OUO -- one updates other
# ---------------------------------------------------------------------------


def test_ouo_partial_fill_shrinks_peer_quantity():
    """OUO: partial fill on TP shrinks SL's remaining quantity."""
    mgr = ContingencyManager()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("ouo-1"),
            orders=[tp, sl],
            contingency_type=ContingencyType.OUO,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.PARTIALLY_FILLED,
        cumulative_quantity=Decimal("4"),
    )
    assert len(commands) == 1
    cmd = commands[0]
    assert cmd.action is ContingencyAction.UPDATE_QUANTITY
    assert cmd.target_order_id.value == "sl-1"
    assert cmd.new_quantity == Decimal("6")


def test_ouo_full_fill_cancels_peer():
    """OUO: when one side fully fills, the peer is canceled (degenerate OCO)."""
    mgr = ContingencyManager()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("ouo-2"),
            orders=[tp, sl],
            contingency_type=ContingencyType.OUO,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.FILLED,
        cumulative_quantity=Decimal("10"),
    )
    assert len(commands) == 1
    assert commands[0].action is ContingencyAction.CANCEL


# ---------------------------------------------------------------------------
# OTO -- one triggers other
# ---------------------------------------------------------------------------


def test_oto_parent_fill_submits_children():
    """OTO: filling the entry order submits the take-profit + stop-loss bracket."""
    mgr = ContingencyManager()
    entry = _entry()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("oto-1"),
            orders=[entry, tp, sl],
            contingency_type=ContingencyType.OTO,
            parent_order_id=entry.client_order_id,
        )
    )

    commands = mgr.on_execution_report(
        client_order_id=entry.client_order_id,
        order_status=OrderStatus.FILLED,
    )
    submit_targets = {
        c.target_order_id.value
        for c in commands
        if c.action is ContingencyAction.SUBMIT
    }
    assert submit_targets == {"tp-1", "sl-1"}


def test_oto_child_fill_does_not_trigger_anything():
    """OTO: filling a child (after parent fired) doesn't re-trigger children."""
    mgr = ContingencyManager()
    entry = _entry()
    tp = _take_profit()
    sl = _stop_loss()
    mgr.register(
        OrderList(
            order_list_id=OrderListId("oto-2"),
            orders=[entry, tp, sl],
            contingency_type=ContingencyType.OTO,
            parent_order_id=entry.client_order_id,
        )
    )

    # Activate children
    mgr.on_execution_report(
        client_order_id=entry.client_order_id,
        order_status=OrderStatus.FILLED,
    )
    # Now a child fills
    commands = mgr.on_execution_report(
        client_order_id=tp.client_order_id,
        order_status=OrderStatus.FILLED,
    )
    # In OTO the child filling doesn't trigger anything (it's not an OCO).
    assert all(c.action is not ContingencyAction.SUBMIT for c in commands)


# ---------------------------------------------------------------------------
# OrderList validation
# ---------------------------------------------------------------------------


def test_orderlist_post_init_crosslinks_peers():
    """OrderList.__post_init__ stamps order_list_id + linked_order_ids on every order."""
    tp = _take_profit()
    sl = _stop_loss()
    ol = OrderList(
        order_list_id=OrderListId("oco-cross"),
        orders=[tp, sl],
        contingency_type=ContingencyType.OCO,
    )
    assert tp.order_list_id.value == "oco-cross"
    assert sl.order_list_id.value == "oco-cross"
    assert tp.linked_order_ids[0].value == "sl-1"
    assert sl.linked_order_ids[0].value == "tp-1"


def test_orderlist_oco_requires_two_orders():
    ol = OrderList(
        order_list_id=OrderListId("oco-bad"),
        orders=[_take_profit()],
        contingency_type=ContingencyType.OCO,
    )
    violations = ol.validate()
    assert any("OCO" in v for v in violations)


def test_orderlist_oto_requires_parent_in_orders():
    """OTO must reference a parent that exists in ``orders``."""
    tp = _take_profit()
    sl = _stop_loss()
    ol = OrderList(
        order_list_id=OrderListId("oto-bad"),
        orders=[tp, sl],
        contingency_type=ContingencyType.OTO,
        parent_order_id=ClientOrderId("nonexistent"),
    )
    violations = ol.validate()
    assert any("OTO parent" in v for v in violations)
