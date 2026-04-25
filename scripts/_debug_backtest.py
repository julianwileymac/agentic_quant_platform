"""Temporary debug script to trace every fill and find the numerical blow-up."""
from __future__ import annotations

import pandas as pd

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.engine import EventDrivenBacktester
from aqp.core.types import Symbol
from aqp.data.duckdb_engine import DuckDBHistoryProvider
from aqp.strategies.execution import MarketOrderExecution
from aqp.strategies.framework import FrameworkAlgorithm
from aqp.strategies.mean_reversion import MeanReversionAlpha
from aqp.strategies.portfolio import EqualWeightPortfolio
from aqp.strategies.risk_models import BasicRiskModel
from aqp.strategies.universes import StaticUniverse

_orig_fill = SimulatedBrokerage._apply_fill


def _logged_fill(self, order, fill_price, ts):
    trade = _orig_fill(self, order, fill_price, ts)
    n = len(self.trades)
    if n <= 30 or n % 25 == 0:
        pos_list = [
            (k, v.direction.value, round(v.quantity, 2), round(v.average_price, 2))
            for k, v in self.positions.items()
        ]
        print(
            f"T{n:03d} {order.side.value:4} {order.symbol.vt_symbol:15} "
            f"qty={order.quantity:.2f} px={fill_price:.2f} cash={self.cash:.2f} pos={pos_list}"
        )
    return trade


def _logged_mtm(self, prices):
    equity = _orig_mtm(self, prices)
    return equity


_orig_mtm = SimulatedBrokerage.mark_to_market
SimulatedBrokerage._apply_fill = _logged_fill


def main():
    provider = DuckDBHistoryProvider()
    syms = [Symbol(ticker=s) for s in ["SPY", "AAPL", "MSFT", "GOOGL", "AMZN"]]
    bars = provider.get_bars(syms, pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-31"))
    print(f"bars: {len(bars)} rows, {bars['timestamp'].nunique()} days")

    strategy = FrameworkAlgorithm(
        universe_model=StaticUniverse(symbols=["SPY", "AAPL", "MSFT", "GOOGL", "AMZN"]),
        alpha_model=MeanReversionAlpha(lookback=20, z_threshold=2.0),
        portfolio_model=EqualWeightPortfolio(max_positions=5),
        risk_model=BasicRiskModel(max_position_pct=0.20, max_drawdown_pct=0.15),
        execution_model=MarketOrderExecution(),
        rebalance_every=1,
    )
    engine = EventDrivenBacktester(initial_cash=100000, commission_pct=0.0005, slippage_bps=2.0)
    result = engine.run(strategy, bars)
    print(f"n trades: {len(result.trades)}")
    print(f"final equity: {result.final_equity:.2f}")
    print(f"equity curve head:\n{result.equity_curve.head(30)}")
    print(f"equity curve tail:\n{result.equity_curve.tail(10)}")


if __name__ == "__main__":
    main()
