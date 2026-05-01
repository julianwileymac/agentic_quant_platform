from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
from pandas.testing import assert_series_equal

from aqp.backtest.engine import EventDrivenBacktester
from aqp.backtest.replay import diff_event_logs, replay_event_log
from aqp.core.interfaces import IStrategy
from aqp.core.types import OrderRequest, OrderSide, OrderType


class _BuyOnceStrategy(IStrategy):
    strategy_id = "event-replay-test"

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
                    quantity=5,
                )
            ]
        )

    def on_order_update(self, order) -> None:
        return None


def test_replay_event_log_reconstructs_equity_and_trades() -> None:
    start = datetime(2025, 1, 1)
    bars = pd.DataFrame(
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
    result = EventDrivenBacktester(initial_cash=10_000).run(
        _BuyOnceStrategy(), bars
    )

    replayed = replay_event_log(result.event_log, initial_cash=10_000)

    assert not diff_event_logs(result.event_log, replayed.event_log)
    assert_series_equal(result.equity_curve, replayed.equity_curve)
    assert len(result.trades) == len(replayed.trades)
    assert result.final_equity == replayed.final_equity
