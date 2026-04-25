"""End-to-end test for the LocalSimulator backtest path."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aqp.backtest.local_simulation import LocalSimulator


class _BuyAndHold:
    strategy_id = "buy-and-hold"

    def on_bar(self, bar, context):
        # Go long on the very first bar and never trade again.
        if context.get("positions"):
            return
        from aqp.core.types import OrderRequest, OrderSide, OrderType

        yield OrderRequest(
            symbol=bar.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10.0,
            strategy_id=self.strategy_id,
        )

    def on_order_update(self, order):  # noqa: D401 — required by IStrategy
        pass


def _write_csv(tmp_path: Path) -> Path:
    dates = pd.date_range("2023-01-02", periods=60, freq="B")
    close = 100 * (1 + 0.001 * np.arange(len(dates)))
    df = pd.DataFrame(
        {
            "timestamp": dates,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": 1_000_000,
        }
    )
    path = tmp_path / "AAPL_LOCAL.csv"
    df.to_csv(path, index=False)
    return tmp_path


def test_local_simulator_runs_csv(tmp_path: Path):
    root = _write_csv(tmp_path)
    sim = LocalSimulator(source_path=root, format="csv", glob="*.csv")
    bars = sim.load_bars()
    assert not bars.empty
    assert "vt_symbol" in bars.columns

    result = sim.run(
        _BuyAndHold(),
        initial_cash=100_000.0,
        commission_pct=0.0,
        slippage_bps=0.0,
    )
    assert result.final_equity > 0
    assert result.initial_cash == 100_000.0
    assert len(result.equity_curve) > 0
