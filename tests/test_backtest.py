"""Smoke tests for the backtest engine using in-memory synthetic data."""
from __future__ import annotations

import pandas as pd

from aqp.backtest.engine import EventDrivenBacktester
from aqp.backtest.metrics import sharpe_ratio, summarise
from aqp.backtest.vectorized import vector_backtest
from aqp.strategies.execution import MarketOrderExecution
from aqp.strategies.framework import FrameworkAlgorithm
from aqp.strategies.mean_reversion import MeanReversionAlpha
from aqp.strategies.portfolio import EqualWeightPortfolio
from aqp.strategies.risk_models import BasicRiskModel
from aqp.strategies.universes import StaticUniverse


def test_event_driven_runs(synthetic_bars: pd.DataFrame) -> None:
    strategy = FrameworkAlgorithm(
        universe_model=StaticUniverse(symbols=["AAA", "BBB", "CCC"]),
        alpha_model=MeanReversionAlpha(lookback=10, z_threshold=1.0),
        portfolio_model=EqualWeightPortfolio(max_positions=3),
        risk_model=BasicRiskModel(max_position_pct=0.35, max_drawdown_pct=0.5),
        execution_model=MarketOrderExecution(),
        rebalance_every=5,
    )
    engine = EventDrivenBacktester(initial_cash=50000)
    result = engine.run(strategy, synthetic_bars)
    assert len(result.equity_curve) > 0
    assert result.summary["n_bars"] > 0


def test_sharpe_ratio_sanity() -> None:
    rng = pd.Series([0.001] * 252)
    assert sharpe_ratio(rng) > 0


def test_vector_backtest_runs(synthetic_bars: pd.DataFrame) -> None:
    frame = synthetic_bars.copy()
    frame["signal"] = 0.2
    result = vector_backtest(frame, signal_column="signal")
    assert "summary" in result
    assert "equity_curve" in result


def test_summarise_on_empty() -> None:

    s = summarise(pd.Series([], dtype=float))
    assert s["sharpe"] == 0.0
    assert s["max_drawdown"] == 0.0
