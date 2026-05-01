from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from aqp.backtest.engine import EventDrivenBacktester
from aqp.core.interfaces import IStrategy
from aqp.core.types import EventType, OrderRequest, OrderSide, OrderType


class _BuyOnceStrategy(IStrategy):
    strategy_id = "event-bus-test"

    def __init__(self) -> None:
        self._sent = False

    def on_bar(self, bar, context):
        if self._sent:
            return iter(())
        self._sent = True
        return iter(
            [
                OrderRequest(
                    symbol=bar.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=10,
                )
            ]
        )

    def on_order_update(self, order) -> None:
        return None


def _bars() -> pd.DataFrame:
    start = datetime(2025, 1, 1)
    return pd.DataFrame(
        [
            {
                "timestamp": start + timedelta(days=i),
                "vt_symbol": "SPY.NASDAQ",
                "open": 100.0 + i,
                "high": 101.0 + i,
                "low": 99.0 + i,
                "close": 100.0 + i,
                "volume": 1000,
            }
            for i in range(5)
        ]
    )


def test_event_driven_backtester_logs_bus_events() -> None:
    result = EventDrivenBacktester(initial_cash=10_000).run(
        _BuyOnceStrategy(), _bars()
    )

    event_types = [event.type for event in result.event_log]
    assert EventType.MARKET in event_types
    assert EventType.ORDER in event_types
    assert EventType.FILL in event_types
    assert result.event_log
    assert len(result.trades) == 1
    assert len(result.equity_curve) == 5


def test_order_event_messages_capture_broker_order_id() -> None:
    result = EventDrivenBacktester(initial_cash=10_000).run(
        _BuyOnceStrategy(), _bars()
    )

    order_events = [e for e in result.event_log if e.type == EventType.ORDER]
    assert order_events
    assert all(e.order_id for e in order_events)
