"""Tests for the Phase 2 amendment manager + atomic request id counter."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from aqp.core.domain.enums import OrderSide, OrderType
from aqp.core.domain.identifiers import (
    ClientOrderId,
    InstrumentId,
    Symbol2,
    Venue,
)
from aqp.core.domain.orders import LimitOrder, StopMarketOrder
from aqp.trading.execution.amendment import (
    AmendmentManager,
    AmendmentRequest,
    AmendmentRouting,
    AtomicRequestIdCounter,
)


def _iid(sym: str = "AAPL") -> InstrumentId:
    return InstrumentId(Symbol2(sym), Venue("NASDAQ"))


def _limit_order(qty: Decimal = Decimal("10"), price: Decimal = Decimal("100")) -> LimitOrder:
    return LimitOrder(
        client_order_id=ClientOrderId("client-1"),
        instrument_id=_iid(),
        order_side=OrderSide.BUY,
        quantity=qty,
        order_type=OrderType.LIMIT,
        price=price,
    )


def _stop_order() -> StopMarketOrder:
    return StopMarketOrder(
        client_order_id=ClientOrderId("client-2"),
        instrument_id=_iid(),
        order_side=OrderSide.SELL,
        quantity=Decimal("10"),
        order_type=OrderType.STOP_MARKET,
        trigger_price=Decimal("180"),
    )


# ---------------------------------------------------------------------------
# Counter
# ---------------------------------------------------------------------------


def test_atomic_counter_starts_at_one_and_increments_monotonically():
    counter = AtomicRequestIdCounter()
    a = counter.next_id()
    b = counter.next_id()
    c = counter.next_id()
    assert a == 1
    assert b == 2
    assert c == 3


def test_atomic_counter_custom_start():
    counter = AtomicRequestIdCounter(_start=100)
    assert counter.next_id() == 100
    assert counter.next_id() == 101


def test_atomic_counter_is_threadsafe():
    """Concurrent next_id() calls produce a gap-free monotonic sequence."""
    import threading

    counter = AtomicRequestIdCounter()
    results = []

    def worker():
        for _ in range(100):
            results.append(counter.next_id())

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 1000
    assert len(set(results)) == 1000  # no duplicates
    assert min(results) == 1
    assert max(results) == 1000


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_routing_trigger_price_change_prefers_ws_amend():
    """Stop-trigger amendments are WS-amendable because the order isn't on the book."""
    mgr = AmendmentManager(
        ws_amend=AsyncMock(return_value=_stop_order()),
        cancel_resubmit=AsyncMock(),
    )
    routing = mgr._select_routing(  # type: ignore[attr-defined]
        AmendmentRequest(
            client_order_id=ClientOrderId("client-2"),
            trigger_price=Decimal("175"),
        ),
        _stop_order(),
    )
    assert routing is AmendmentRouting.WS_AMEND


def test_routing_quantity_down_on_limit_uses_ws_amend():
    """Reducing a limit-order's quantity preserves queue position via WS amend."""
    mgr = AmendmentManager(
        ws_amend=AsyncMock(),
        cancel_resubmit=AsyncMock(),
    )
    order = _limit_order(qty=Decimal("10"))
    routing = mgr._select_routing(
        AmendmentRequest(
            client_order_id=order.client_order_id,
            quantity=Decimal("5"),
        ),
        order,
    )
    assert routing is AmendmentRouting.WS_AMEND


def test_routing_price_change_uses_cancel_resubmit():
    """Price changes lose queue position -> cancel + resubmit is correct."""
    mgr = AmendmentManager(
        ws_amend=AsyncMock(),
        cancel_resubmit=AsyncMock(),
    )
    routing = mgr._select_routing(
        AmendmentRequest(
            client_order_id=ClientOrderId("client-1"),
            price=Decimal("99"),
        ),
        _limit_order(),
    )
    assert routing is AmendmentRouting.CANCEL_RESUBMIT


def test_routing_quantity_up_default_uses_cancel_resubmit():
    """Default policy doesn't WS-amend quantity increases."""
    mgr = AmendmentManager(
        ws_amend=AsyncMock(),
        cancel_resubmit=AsyncMock(),
    )
    order = _limit_order(qty=Decimal("10"))
    routing = mgr._select_routing(
        AmendmentRequest(
            client_order_id=order.client_order_id,
            quantity=Decimal("20"),
        ),
        order,
    )
    assert routing is AmendmentRouting.CANCEL_RESUBMIT


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_amend_routes_to_ws_amend_for_trigger_price():
    order = _stop_order()
    ws_amend = AsyncMock(return_value=order)
    cancel_resubmit = AsyncMock()
    mgr = AmendmentManager(ws_amend=ws_amend, cancel_resubmit=cancel_resubmit)

    result = await mgr.amend(
        AmendmentRequest(
            client_order_id=order.client_order_id,
            trigger_price=Decimal("175"),
        ),
        current_order=order,
    )
    assert result.routing is AmendmentRouting.WS_AMEND
    ws_amend.assert_awaited_once()
    cancel_resubmit.assert_not_awaited()


@pytest.mark.asyncio
async def test_amend_falls_back_to_cancel_resubmit_on_ws_failure():
    """When WS amend raises, the manager falls back to cancel + resubmit."""
    order = _stop_order()
    ws_amend = AsyncMock(side_effect=RuntimeError("WS dead"))
    cancel_resubmit = AsyncMock(return_value=order)
    mgr = AmendmentManager(ws_amend=ws_amend, cancel_resubmit=cancel_resubmit)

    result = await mgr.amend(
        AmendmentRequest(
            client_order_id=order.client_order_id,
            trigger_price=Decimal("175"),
        ),
        current_order=order,
    )
    assert result.routing is AmendmentRouting.CANCEL_RESUBMIT
    ws_amend.assert_awaited_once()
    cancel_resubmit.assert_awaited_once()


@pytest.mark.asyncio
async def test_amend_rejects_empty_request():
    order = _limit_order()
    mgr = AmendmentManager(
        ws_amend=AsyncMock(),
        cancel_resubmit=AsyncMock(),
    )

    result = await mgr.amend(
        AmendmentRequest(client_order_id=order.client_order_id),
        current_order=order,
    )
    assert result.routing is AmendmentRouting.REJECTED
    assert "empty" in (result.error or "")
