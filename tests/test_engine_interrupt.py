"""Tests for the EventDrivenBacktester interrupt hook."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import pytest

from aqp.backtest.engine import EventDrivenBacktester
from aqp.backtest.interrupts import (
    InterruptRequest,
    InterruptResolution,
    find_first_matching_rule,
    order_matches_rule,
)
from aqp.core.interfaces import IStrategy
from aqp.core.types import BarData, OrderData, OrderRequest, OrderSide, OrderType, Symbol


class _BuyOnceStrategy(IStrategy):
    """Submit a single market BUY for the first bar we see, then stay quiet."""

    strategy_id = "test-buy-once"

    def __init__(self, symbol: str, quantity: float = 100.0) -> None:
        self.symbol = symbol
        self.quantity = quantity
        self._submitted = False

    def on_order_update(self, order: OrderData) -> None:
        return None

    def on_bar(self, bar: BarData, context: dict[str, Any]) -> Iterator[OrderRequest]:
        if self._submitted:
            return iter(())
        if bar.symbol.vt_symbol != self.symbol:
            return iter(())
        self._submitted = True
        return iter(
            [
                OrderRequest(
                    symbol=Symbol.parse(self.symbol),
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=self.quantity,
                    price=None,
                )
            ]
        )


def _bars() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=5)
    rng = np.random.default_rng(1)
    return pd.DataFrame(
        [
            {
                "timestamp": ts,
                "vt_symbol": "AAA.NASDAQ",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.5 + i,
                "volume": float(rng.integers(1_000_000, 5_000_000)),
            }
            for i, ts in enumerate(dates)
        ]
    )


def test_order_matches_rule_actions() -> None:
    rule = {"actions": ["BUY"], "min_size_pct": 0.0}
    order = {"side": "BUY", "size_pct": 0.5}
    assert order_matches_rule(order, rule)

    rule_sell = {"actions": ["SELL"]}
    assert not order_matches_rule(order, rule_sell)


def test_find_first_matching_rule_returns_first_hit() -> None:
    orders = [{"side": "BUY", "quantity": 10, "price": 50}]
    rules = [
        {"actions": ["SELL"]},
        {"name": "buy_rule", "actions": ["BUY"]},
    ]
    match = find_first_matching_rule(orders, rules)
    assert match is not None
    name, matched = match
    assert name == "buy_rule"
    assert len(matched) == 1


def test_engine_continues_when_handler_returns_continue() -> None:
    handler_calls = []

    def handler(req: InterruptRequest) -> InterruptResolution:
        handler_calls.append(req)
        return InterruptResolution.cont()

    engine = EventDrivenBacktester(
        initial_cash=100_000,
        commission_pct=0.0,
        slippage_bps=0.0,
        interrupt_rules=[{"actions": ["BUY"]}],
        interrupt_handler=handler,
    )
    strat = _BuyOnceStrategy("AAA.NASDAQ", quantity=10)
    result = engine.run(strat, _bars())
    assert handler_calls, "handler should have been invoked at least once"
    assert len(result.orders) == 1
    assert result.orders.iloc[0]["quantity"] == 10


def test_engine_skip_drops_orders() -> None:
    def handler(req: InterruptRequest) -> InterruptResolution:
        return InterruptResolution.skip(note="vetoed")

    engine = EventDrivenBacktester(
        initial_cash=100_000,
        commission_pct=0.0,
        slippage_bps=0.0,
        interrupt_rules=[{"actions": ["BUY"]}],
        interrupt_handler=handler,
    )
    result = engine.run(_BuyOnceStrategy("AAA.NASDAQ", quantity=10), _bars())
    assert len(result.orders) == 0
    assert len(result.trades) == 0


def test_engine_replace_substitutes_orders() -> None:
    def handler(req: InterruptRequest) -> InterruptResolution:
        # Replace with a smaller size.
        return InterruptResolution.replace(
            replacement_orders=[
                {"index": 0, "quantity": 5, "side": "BUY", "order_type": "MARKET"}
            ]
        )

    engine = EventDrivenBacktester(
        initial_cash=100_000,
        commission_pct=0.0,
        slippage_bps=0.0,
        interrupt_rules=[{"actions": ["BUY"]}],
        interrupt_handler=handler,
    )
    result = engine.run(_BuyOnceStrategy("AAA.NASDAQ", quantity=10), _bars())
    assert len(result.orders) == 1
    assert result.orders.iloc[0]["quantity"] == 5
