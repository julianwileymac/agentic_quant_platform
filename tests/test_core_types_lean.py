"""Lean-style core type expansion tests."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from aqp.core.types import (
    BarData,
    Cash,
    CashBook,
    DataNormalizationMode,
    OrderData,
    OrderEvent,
    OrderSide,
    OrderStatus,
    OrderTicket,
    OrderType,
    QuoteBar,
    Resolution,
    SecurityHolding,
    SubscriptionDataConfig,
    Symbol,
    TickType,
    TradeBar,
    iter_subscriptions,
)


def test_trade_bar_is_bar_data_alias():
    assert TradeBar is BarData


def test_resolution_to_timedelta():
    assert Resolution.MINUTE.to_timedelta() == timedelta(minutes=1)
    assert Resolution.DAILY.to_timedelta() == timedelta(days=1)
    assert Resolution.TICK.to_timedelta() == timedelta(0)


def test_resolution_from_interval():
    assert Resolution.from_interval("1m") == Resolution.MINUTE
    assert Resolution.from_interval("1d") == Resolution.DAILY


def test_subscription_data_config_defaults():
    sym = Symbol(ticker="AAPL")
    cfg = SubscriptionDataConfig(symbol=sym)
    assert cfg.resolution == Resolution.DAILY
    assert cfg.tick_type == TickType.TRADE
    assert cfg.normalization == DataNormalizationMode.ADJUSTED
    assert cfg.vt_symbol == "AAPL.NASDAQ"


def test_iter_subscriptions_yields_default_configs():
    symbols = [Symbol(ticker="AAPL"), Symbol(ticker="MSFT")]
    configs = list(iter_subscriptions(symbols, resolution=Resolution.MINUTE))
    assert len(configs) == 2
    assert all(isinstance(c, SubscriptionDataConfig) for c in configs)
    assert {c.vt_symbol for c in configs} == {"AAPL.NASDAQ", "MSFT.NASDAQ"}


def test_quote_bar_mid_and_spread():
    qb = QuoteBar(
        symbol=Symbol(ticker="AAPL"),
        timestamp=datetime(2026, 1, 2, 9, 30),
        bid_open=100.0, bid_high=101.0, bid_low=99.0, bid_close=100.5,
        ask_open=100.2, ask_high=101.2, ask_low=99.2, ask_close=100.7,
    )
    assert qb.mid_close == pytest.approx(100.6)
    assert qb.spread_close == pytest.approx(0.2)


def test_cash_book_total_value():
    cb = CashBook(account_currency="USD")
    cb["USD"] = Cash("USD", 1000)
    cb["EUR"] = Cash("EUR", 100, conversion_rate=1.1)
    assert cb.total_value_in_account_currency == pytest.approx(1110.0)


def test_security_holding_from_position():
    from aqp.core.types import Direction, PositionData

    pos = PositionData(
        symbol=Symbol(ticker="AAPL"),
        direction=Direction.LONG,
        quantity=10.0,
        average_price=150.0,
    )
    holding = SecurityHolding.from_position(pos)
    assert holding.quantity == 10.0
    assert holding.average_price == 150.0
    assert holding.notional == pytest.approx(1500.0)


def test_order_ticket_tracks_events():
    order = OrderData(
        order_id="o1",
        gateway="sim",
        symbol=Symbol(ticker="AAPL"),
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=10.0,
        status=OrderStatus.SUBMITTING,
    )
    ticket = OrderTicket(order=order)
    # Partial fill
    ticket.append_event(
        OrderEvent(
            order_id="o1",
            timestamp=datetime.utcnow(),
            status=OrderStatus.PARTIAL,
            direction=OrderSide.BUY,
            fill_price=100.0,
            fill_quantity=4.0,
        )
    )
    assert ticket.order.filled_quantity == 4.0
    assert ticket.order.average_fill_price == pytest.approx(100.0)
    # Full fill at a higher price → running VWAP
    ticket.append_event(
        OrderEvent(
            order_id="o1",
            timestamp=datetime.utcnow(),
            status=OrderStatus.FILLED,
            direction=OrderSide.BUY,
            fill_price=110.0,
            fill_quantity=6.0,
        )
    )
    assert ticket.order.filled_quantity == 10.0
    assert ticket.order.average_fill_price == pytest.approx(106.0)
    assert ticket.order.status == OrderStatus.FILLED
    assert ticket.is_active() is False


def test_slice_envelope():
    from aqp.core.slice import Slice

    sym = Symbol(ticker="AAPL")
    bar = BarData(
        symbol=sym,
        timestamp=datetime(2026, 1, 2),
        open=100.0, high=101.0, low=99.0, close=100.5, volume=1_000_000,
    )
    s = Slice.from_bars(datetime(2026, 1, 2), [bar])
    assert sym in s
    assert s.price(sym) == 100.5
    assert s.bar(sym) is bar
    assert not s.is_empty
