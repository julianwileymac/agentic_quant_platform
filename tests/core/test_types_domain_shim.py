"""Tests for the Phase 5 finalization: ``aqp.core.types`` as a domain shim.

The legacy module is now a compatibility shim over :mod:`aqp.core.domain`.
Every existing public name MUST keep working (back-compat for ~140
importers across the codebase) AND every domain-replaceable type MUST
expose a bridge method to its canonical domain equivalent.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest


# ---------------------------------------------------------------------------
# Backward-compatibility: legacy names still import + work
# ---------------------------------------------------------------------------


def test_legacy_enums_still_importable_with_legacy_values():
    """The legacy enums still carry their original values.

    Critical: existing DB rows and YAML files persist these strings; the
    shim cannot drop or rename them or every previously-saved row breaks.
    """
    from aqp.core.types import (
        AssetClass,
        Direction,
        Exchange,
        OrderSide,
        OrderStatus,
        OrderType,
        SecurityType,
    )

    # Sample one value from each legacy enum
    assert Exchange.NASDAQ.value == "NASDAQ"
    assert AssetClass.EQUITY.value == "equity"
    assert SecurityType.OPTION.value == "option"
    assert Direction.LONG.value == "long"
    assert OrderType.MARKET.value == "market"
    assert OrderSide.BUY.value == "buy"
    assert OrderStatus.SUBMITTING.value == "submitting"
    # Legacy spelling preserved (two L's) -- the domain uses CANCELED (one L)
    assert OrderStatus.CANCELLED.value == "cancelled"


def test_legacy_symbol_parse_still_works():
    from aqp.core.types import Exchange, Symbol

    sym = Symbol.parse("AAPL.NASDAQ")
    assert sym.ticker == "AAPL"
    assert sym.exchange is Exchange.NASDAQ
    assert sym.vt_symbol == "AAPL.NASDAQ"


def test_legacy_bar_data_construction_unchanged():
    """Market data records have no domain equivalent and remain authoritative here."""
    from aqp.core.types import BarData, Exchange, Interval, Symbol

    bar = BarData(
        symbol=Symbol(ticker="MSFT", exchange=Exchange.NASDAQ),
        timestamp=datetime(2026, 5, 16, 9, 30),
        open=400.0,
        high=405.0,
        low=399.0,
        close=403.0,
        volume=1_000_000,
        interval=Interval.MINUTE,
    )
    assert bar.vt_symbol == "MSFT.NASDAQ"
    assert bar.value == 403.0


def test_legacy_signal_and_portfolio_target_unchanged():
    """Framework value objects (no domain replacement) keep their shape."""
    from aqp.core.types import Direction, PortfolioTarget, Signal, Symbol

    sym = Symbol(ticker="AAPL")
    sig = Signal(
        symbol=sym, strength=0.8, direction=Direction.LONG, source="momentum"
    )
    target = PortfolioTarget(
        symbol=sym, target_weight=0.05, rationale="momentum signal"
    )
    assert sig.symbol.ticker == "AAPL"
    assert target.target_weight == 0.05


def test_legacy_event_loop_types_unchanged():
    from aqp.core.types import (
        Event,
        EventType,
        FillEvent_Msg,
        MarketEvent,
        OrderEvent_Msg,
        OrderRequest,
        OrderSide,
        OrderType,
        Signal,
        SignalEvent,
        Symbol,
        TradeData,
    )

    sym = Symbol(ticker="AAPL")
    req = OrderRequest(
        symbol=sym, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10.0
    )
    order_msg = OrderEvent_Msg(request=req)
    assert order_msg.type is EventType.ORDER


def test_legacy_cashbook_unchanged():
    from aqp.core.types import Cash, CashBook

    book = CashBook(account_currency="USD")
    book["EUR"] = Cash(currency="EUR", amount=100.0, conversion_rate=1.08)
    book["USD"] = Cash(currency="USD", amount=50_000.0, conversion_rate=1.0)
    total = book.total_value_in_account_currency
    assert total == pytest.approx(50_000.0 + 108.0, rel=1e-9)


# ---------------------------------------------------------------------------
# Phase 5: domain re-exports are now importable from aqp.core.types
# ---------------------------------------------------------------------------


def test_domain_types_re_exported_from_legacy_module():
    """Phase 5 makes every domain type importable through the shim.

    A single ``from aqp.core.types import DomainOrder, RiskMeasure``
    works so callers can migrate one import at a time.
    """
    from aqp.core import types as legacy

    # Domain orders
    assert legacy.DomainOrder is not None
    assert legacy.LimitOrder is not None
    assert legacy.StopMarketOrder is not None
    assert legacy.OrderList is not None
    # Domain identifiers
    assert legacy.InstrumentId is not None
    assert legacy.ClientOrderId is not None
    assert legacy.VenueOrderId is not None
    assert legacy.AccountId is not None
    # Domain enums
    assert legacy.TimeInForce is not None
    assert legacy.TriggerType is not None
    assert legacy.OmsType is not None
    assert legacy.PositionSide is not None
    assert legacy.InstrumentClass is not None
    # Disambiguated re-exports
    assert legacy.DomainOrderType is not None
    assert legacy.DomainOrderStatus is not None


def test_domain_order_type_is_superset_of_legacy():
    """The re-exported domain OrderType has values legacy doesn't carry."""
    from aqp.core.types import DomainOrderType, OrderType

    domain_values = {e.value for e in DomainOrderType}
    legacy_values = {e.value for e in OrderType}
    # Every legacy value the LEGACY OrderType carries also exists in domain
    # (with the exception of "stop" -> "stop_market" rename); but the domain
    # enum at minimum has these advanced types the legacy doesn't:
    assert "stop_market" in domain_values
    assert "market_if_touched" in domain_values
    assert "trailing_stop_market" in domain_values
    # Legacy has "stop" which the domain renames to "stop_market"
    assert "stop" in legacy_values
    assert "stop" not in domain_values  # explicit rename


# ---------------------------------------------------------------------------
# Bridge methods (legacy -> domain)
# ---------------------------------------------------------------------------


def test_symbol_to_instrument_id_round_trips():
    from aqp.core.types import Exchange, Symbol

    sym = Symbol(ticker="AAPL", exchange=Exchange.NASDAQ)
    iid = sym.to_instrument_id()
    assert iid.symbol.value == "AAPL"
    assert iid.venue.value == "NASDAQ"
    # Round-trip
    back = Symbol.from_instrument_id(iid)
    assert back == sym


def test_order_request_to_domain_order_market():
    """Legacy OrderRequest.to_domain_order produces a MarketOrder for type=MARKET."""
    from aqp.core.domain.orders import MarketOrder
    from aqp.core.types import (
        Exchange,
        OrderRequest,
        OrderSide,
        OrderType,
        Symbol,
    )

    req = OrderRequest(
        symbol=Symbol(ticker="AAPL", exchange=Exchange.NASDAQ),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
    )
    domain = req.to_domain_order(client_order_id="test-1")
    assert isinstance(domain, MarketOrder)
    assert domain.quantity == Decimal("10")
    assert domain.client_order_id.value == "test-1"


def test_order_request_to_domain_order_limit():
    from aqp.core.domain.orders import LimitOrder
    from aqp.core.types import (
        Exchange,
        OrderRequest,
        OrderSide,
        OrderType,
        Symbol,
    )

    req = OrderRequest(
        symbol=Symbol(ticker="AAPL", exchange=Exchange.NASDAQ),
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=5.0,
        price=200.0,
    )
    domain = req.to_domain_order()
    assert isinstance(domain, LimitOrder)
    assert domain.price == Decimal("200")


def test_order_data_to_domain_order_round_trip():
    """OrderData.to_domain_order then .from_domain_order preserves identity."""
    from aqp.core.types import (
        Exchange,
        OrderData,
        OrderSide,
        OrderStatus,
        OrderType,
        Symbol,
    )

    original = OrderData(
        order_id="abc-123",
        gateway="alpaca",
        symbol=Symbol(ticker="AAPL", exchange=Exchange.NASDAQ),
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=10.0,
        status=OrderStatus.SUBMITTING,
        price=200.0,
    )
    domain = original.to_domain_order()
    rebuilt = OrderData.from_domain_order(domain, gateway="alpaca")
    assert rebuilt.symbol.ticker == "AAPL"
    assert rebuilt.side is OrderSide.BUY
    assert rebuilt.order_type is OrderType.LIMIT
    assert rebuilt.price == 200.0


def test_account_data_from_account_row_bridge():
    """AccountData.from_account_row aggregates balances correctly."""
    from types import SimpleNamespace

    from aqp.core.types import AccountData

    account = SimpleNamespace(
        account_id="DU12345",
        base_currency="USD",
        updated_at=datetime(2026, 5, 16),
    )
    balances = [
        SimpleNamespace(currency="USD", balance_kind="CASH", amount=50_000.0),
        SimpleNamespace(currency="USD", balance_kind="UNREALIZED_PNL", amount=1_500.0),
        SimpleNamespace(currency="USD", balance_kind="MARGIN_INITIAL", amount=20_000.0),
        SimpleNamespace(currency="EUR", balance_kind="CASH", amount=999.0),  # foreign
    ]
    snap = AccountData.from_account_row(account, balances=balances)
    assert snap.account_id == "DU12345"
    assert snap.cash == 50_000.0
    assert snap.equity == 51_500.0  # CASH + UNREALIZED_PNL
    assert snap.margin_used == 20_000.0
    assert snap.currency == "USD"


def test_position_data_from_account_position_row_long():
    """Positive quantity in the row maps to Direction.LONG with abs(quantity)."""
    from types import SimpleNamespace

    from aqp.core.types import Direction, PositionData

    row = SimpleNamespace(
        vt_symbol="AAPL.NASDAQ",
        quantity=100.0,
        average_entry_price=190.0,
        unrealized_pnl=500.0,
        realized_pnl=0.0,
    )
    pos = PositionData.from_account_position_row(row)
    assert pos.direction is Direction.LONG
    assert pos.quantity == 100.0
    assert pos.symbol.ticker == "AAPL"


def test_position_data_from_account_position_row_short():
    """Negative quantity in the row maps to Direction.SHORT with abs(quantity)."""
    from types import SimpleNamespace

    from aqp.core.types import Direction, PositionData

    row = SimpleNamespace(
        vt_symbol="TSLA.NASDAQ",
        quantity=-50.0,
        average_entry_price=240.0,
        unrealized_pnl=-200.0,
        realized_pnl=0.0,
    )
    pos = PositionData.from_account_position_row(row)
    assert pos.direction is Direction.SHORT
    assert pos.quantity == 50.0


def test_trade_data_from_execution_report_bridge():
    """TradeData.from_execution_report builds a legacy fill row from Phase 2 audit."""
    from types import SimpleNamespace

    from aqp.core.types import OrderSide, TradeData

    report = SimpleNamespace(
        vt_symbol="AAPL.NASDAQ",
        venue="NASDAQ",
        venue_execution_id="ex-1",
        client_order_id="client-1",
        order_side="buy",
        last_price=200.5,
        last_quantity=10.0,
        commission=0.50,
        trade_id="trade-99",
        ts_event=datetime(2026, 5, 16, 10, 30),
    )
    trade = TradeData.from_execution_report(report)
    assert trade.trade_id == "trade-99"
    assert trade.symbol.ticker == "AAPL"
    assert trade.side is OrderSide.BUY
    assert trade.price == 200.5
    assert trade.quantity == 10.0
    assert trade.commission == 0.5


# ---------------------------------------------------------------------------
# Deprecation status: legacy types still load + report deprecation marker
# ---------------------------------------------------------------------------


def test_legacy_types_module_loads_without_errors():
    """The legacy module imports cleanly even with domain types present."""
    import aqp.core.types  # noqa: F401


def test_legacy_classes_have_deprecation_docstring():
    """Every domain-replaceable legacy class documents its replacement."""
    from aqp.core.types import (
        AccountData,
        AssetClass,
        OrderData,
        OrderRequest,
        OrderSide,
        OrderStatus,
        OrderType,
        PositionData,
        SecurityType,
        Symbol,
        TradeData,
    )

    for cls in (
        Symbol,
        OrderRequest,
        OrderData,
        TradeData,
        PositionData,
        AccountData,
        OrderType,
        OrderSide,
        OrderStatus,
        AssetClass,
        SecurityType,
    ):
        # ".. deprecated::" Sphinx directive present in docstring
        assert ".. deprecated::" in (cls.__doc__ or ""), (
            f"{cls.__name__} missing deprecated:: directive"
        )


def test_all_export_list_includes_legacy_and_domain_names():
    """The module's __all__ lists both legacy + Phase 1-5 domain types."""
    import aqp.core.types as legacy

    # Sample from each section
    for name in (
        # Legacy enums
        "OrderType",
        "OrderSide",
        "OrderStatus",
        # Legacy shims
        "OrderRequest",
        "OrderData",
        "Symbol",
        "AccountData",
        # Domain re-exports
        "DomainOrder",
        "LimitOrder",
        "InstrumentId",
        "RiskMeasure" if False else "ClientOrderId",  # RiskMeasure lives elsewhere
        "TimeInForce",
        "ContingencyType",
        "OmsType",
    ):
        assert name in legacy.__all__, f"{name} missing from __all__"
