"""Tests for the Phase 2 DomainOrder + legacy adapter bridge."""
from __future__ import annotations

from decimal import Decimal

from aqp.core.domain.enums import (
    OrderSide as DomainOrderSide,
    OrderType as DomainOrderType,
    TimeInForce,
)
from aqp.core.domain.identifiers import Symbol2, Venue
from aqp.core.domain.orders import (
    DomainOrder,
    LimitOrder,
    MarketOrder,
    StopMarketOrder,
)
from aqp.core.types import (
    Exchange,
    OrderRequest,
    OrderSide as LegacyOrderSide,
    OrderType as LegacyOrderType,
    Symbol,
)
from aqp.trading.execution.legacy_adapter import (
    domain_order_from_order_request,
    order_data_from_domain_order,
)


def test_domain_order_outside_rth_default_false():
    """Phase 2 flag defaults to False so existing callers don't trip extended-hours."""
    from aqp.core.domain.identifiers import ClientOrderId, InstrumentId

    order = MarketOrder(
        client_order_id=ClientOrderId("test-1"),
        instrument_id=InstrumentId(Symbol2("AAPL"), Venue("NASDAQ")),
        order_side=DomainOrderSide.BUY,
        quantity=Decimal("1"),
        order_type=DomainOrderType.MARKET,
    )
    assert order.outside_rth is False
    assert order.close_position is False
    assert order.post_only is False
    assert order.reduce_only is False


def test_validate_flags_rejects_reduce_only_and_close_position():
    """Mutually exclusive flags raise a validation error."""
    from aqp.core.domain.identifiers import ClientOrderId, InstrumentId

    order = MarketOrder(
        client_order_id=ClientOrderId("test-2"),
        instrument_id=InstrumentId(Symbol2("AAPL"), Venue("NASDAQ")),
        order_side=DomainOrderSide.SELL,
        quantity=Decimal("1"),
        order_type=DomainOrderType.MARKET,
        reduce_only=True,
        close_position=True,
    )
    violations = order.validate_flags()
    assert any("reduce_only and close_position" in v for v in violations)


def test_validate_flags_rejects_post_only_market():
    from aqp.core.domain.identifiers import ClientOrderId, InstrumentId

    order = MarketOrder(
        client_order_id=ClientOrderId("test-3"),
        instrument_id=InstrumentId(Symbol2("AAPL"), Venue("NASDAQ")),
        order_side=DomainOrderSide.BUY,
        quantity=Decimal("1"),
        order_type=DomainOrderType.MARKET,
        post_only=True,
    )
    violations = order.validate_flags()
    assert any("post_only requires a non-market order_type" in v for v in violations)


def test_validate_flags_rejects_gtd_without_date():
    from aqp.core.domain.identifiers import ClientOrderId, InstrumentId

    order = LimitOrder(
        client_order_id=ClientOrderId("test-4"),
        instrument_id=InstrumentId(Symbol2("AAPL"), Venue("NASDAQ")),
        order_side=DomainOrderSide.BUY,
        quantity=Decimal("1"),
        order_type=DomainOrderType.LIMIT,
        price=Decimal("100"),
        time_in_force=TimeInForce.GTD,
    )
    violations = order.validate_flags()
    assert any("good_till_date" in v for v in violations)


# ---------------------------------------------------------------------------
# Legacy adapter round-trip
# ---------------------------------------------------------------------------


def test_legacy_market_request_round_trips_to_domain_market():
    sym = Symbol(ticker="AAPL", exchange=Exchange.NASDAQ)
    req = OrderRequest(
        symbol=sym,
        side=LegacyOrderSide.BUY,
        order_type=LegacyOrderType.MARKET,
        quantity=10.0,
    )
    domain = domain_order_from_order_request(req, gateway="alpaca")
    assert isinstance(domain, MarketOrder)
    assert domain.order_side is DomainOrderSide.BUY
    assert domain.quantity == Decimal("10")
    assert domain.instrument_id.symbol.value == "AAPL"
    assert domain.instrument_id.venue.value == "NASDAQ"


def test_legacy_limit_request_round_trips_to_domain_limit():
    sym = Symbol(ticker="MSFT", exchange=Exchange.NASDAQ)
    req = OrderRequest(
        symbol=sym,
        side=LegacyOrderSide.SELL,
        order_type=LegacyOrderType.LIMIT,
        quantity=5.0,
        price=400.50,
    )
    domain = domain_order_from_order_request(req)
    assert isinstance(domain, LimitOrder)
    assert domain.price == Decimal("400.5")
    assert domain.order_side is DomainOrderSide.SELL


def test_legacy_stop_request_round_trips_to_domain_stop_market():
    sym = Symbol(ticker="AAPL", exchange=Exchange.NASDAQ)
    req = OrderRequest(
        symbol=sym,
        side=LegacyOrderSide.SELL,
        order_type=LegacyOrderType.STOP,
        quantity=10.0,
        stop_price=180.0,
    )
    domain = domain_order_from_order_request(req)
    assert isinstance(domain, StopMarketOrder)
    assert domain.trigger_price == Decimal("180")


def test_domain_to_legacy_order_data():
    from aqp.core.domain.identifiers import ClientOrderId, InstrumentId

    domain = LimitOrder(
        client_order_id=ClientOrderId("client-id-1"),
        instrument_id=InstrumentId(Symbol2("AAPL"), Venue("NASDAQ")),
        order_side=DomainOrderSide.BUY,
        quantity=Decimal("10"),
        order_type=DomainOrderType.LIMIT,
        price=Decimal("190.0"),
    )
    data = order_data_from_domain_order(domain, gateway="alpaca")
    assert data.order_type == LegacyOrderType.LIMIT
    assert data.side == LegacyOrderSide.BUY
    assert data.price == 190.0


def test_tif_normalization_for_legacy_strings():
    """Legacy 'good_til_canceled' string maps to TimeInForce.GTC."""
    sym = Symbol(ticker="AAPL", exchange=Exchange.NASDAQ)
    req = OrderRequest(
        symbol=sym,
        side=LegacyOrderSide.BUY,
        order_type=LegacyOrderType.LIMIT,
        quantity=10.0,
        price=100.0,
        time_in_force="good_til_canceled",
    )
    domain = domain_order_from_order_request(req)
    assert domain.time_in_force is TimeInForce.GTC
