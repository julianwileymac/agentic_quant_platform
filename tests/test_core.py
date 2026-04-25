"""Smoke tests for aqp.core."""
from __future__ import annotations

from aqp.core import (
    BarData,
    Event,
    EventEngine,
    Exchange,
    OrderRequest,
    OrderSide,
    OrderType,
    Symbol,
    build_from_config,
)


def test_symbol_vt_symbol():
    s = Symbol(ticker="AAPL", exchange=Exchange.NASDAQ)
    assert s.vt_symbol == "AAPL.NASDAQ"
    assert Symbol.parse("AAPL.NASDAQ") == s


def test_order_request_creates_order():
    sym = Symbol(ticker="AAPL")
    req = OrderRequest(
        symbol=sym, side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10, price=None
    )
    order = req.create_order(order_id="abc123", gateway="sim")
    assert order.order_id == "abc123"
    assert order.symbol.ticker == "AAPL"
    assert order.is_active()


def test_event_engine_handlers():
    bus = EventEngine()
    seen: list[Event] = []
    bus.register("ping", lambda e: seen.append(e))
    bus.put(Event(type="ping", payload={"x": 1}))
    assert len(seen) == 1
    assert seen[0].payload["x"] == 1


def test_registry_build_from_config():
    obj = build_from_config(
        {
            "class": "StaticUniverse",
            "module_path": "aqp.strategies.universes",
            "kwargs": {"symbols": ["AAPL", "MSFT"]},
        }
    )
    universe = obj.select(None, {})
    assert {s.ticker for s in universe} == {"AAPL", "MSFT"}


def test_bardata_roundtrip():
    sym = Symbol(ticker="SPY")
    bar = BarData(symbol=sym, timestamp=None, open=1.0, high=2.0, low=0.5, close=1.5, volume=100)
    assert bar.vt_symbol == "SPY.NASDAQ"
    assert bar.close == 1.5
