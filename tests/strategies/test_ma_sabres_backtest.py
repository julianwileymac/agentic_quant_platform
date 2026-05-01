"""End-to-end smoke test: MASabres alpha through EventDrivenBacktester.

One of the three canonical platform smoke runs from the inspiration
rehydration plan. Exercises:

- Strategy registration via @register on
  :class:`aqp.strategies.qtradex.alphas.MASabresAlpha`.
- :class:`FrameworkAlgorithm` 5-stage pipeline composition.
- :class:`EventDrivenBacktester` event loop (no network, fully hermetic).
- ``BacktestResult.summary`` field population.
"""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.backtest.engine import BacktestResult, EventDrivenBacktester
from aqp.core.types import Symbol
from aqp.strategies.execution import MarketOrderExecution
from aqp.strategies.framework import FrameworkAlgorithm
from aqp.strategies.portfolio import SignalWeightedPortfolio
from aqp.strategies.qtradex.alphas import MASabresAlpha
from aqp.strategies.risk_models import BasicRiskModel
from aqp.strategies.universes import StaticUniverse


def _build_strategy() -> FrameworkAlgorithm:
    universe = StaticUniverse(symbols=[
        Symbol.parse("AAA.NASDAQ"),
        Symbol.parse("BBB.NASDAQ"),
        Symbol.parse("CCC.NASDAQ"),
    ])
    alpha = MASabresAlpha(windows=(5, 10, 20), threshold_ratio=0.5)
    portfolio = SignalWeightedPortfolio(max_positions=3)
    risk = BasicRiskModel(max_position_pct=0.30, max_drawdown_pct=0.40)
    execution = MarketOrderExecution()
    return FrameworkAlgorithm(
        universe_model=universe,
        alpha_model=alpha,
        portfolio_model=portfolio,
        risk_model=risk,
        execution_model=execution,
        rebalance_every=5,
    )


def test_masabres_backtest_runs_to_completion(synthetic_bars: pd.DataFrame) -> None:
    strategy = _build_strategy()
    engine = EventDrivenBacktester(
        initial_cash=100_000.0,
        commission_pct=0.0010,
        slippage_bps=5.0,
        start="2022-01-01",
        end="2022-12-31",
    )
    result = engine.run(strategy, synthetic_bars)

    assert isinstance(result, BacktestResult), "engine must return a BacktestResult"
    assert not result.equity_curve.empty, "equity curve should be populated"
    assert result.equity_curve.iloc[0] == pytest.approx(100_000.0, rel=0.01), (
        "equity series should start near initial cash"
    )
    assert result.initial_cash == pytest.approx(100_000.0)
    assert result.final_equity > 0, "final equity must be positive"

    # Summary must include the standard set of metrics
    expected_summary_fields = {"total_return", "max_drawdown", "sharpe", "n_trades"}
    missing = expected_summary_fields.difference(result.summary.keys())
    assert not missing, f"missing summary fields: {missing}"

    # Event log carries enough context for replay
    assert len(result.event_log) > 0, "event log should not be empty"


def test_masabres_alpha_produces_signals(synthetic_bars: pd.DataFrame) -> None:
    """Cheap signal-only test that doesn't require running the full engine."""
    alpha = MASabresAlpha(windows=(5, 10, 20), threshold_ratio=0.5)
    universe = [Symbol.parse(s) for s in ["AAA.NASDAQ", "BBB.NASDAQ", "CCC.NASDAQ"]]
    # Use last 200 bars of synthetic data as 'history'
    history = synthetic_bars[synthetic_bars["timestamp"] < "2022-06-01"].tail(1000)
    signals = alpha.generate_signals(history, universe, {"current_time": pd.Timestamp("2022-05-31")})
    # Synthetic data has no guaranteed regime; the test asserts the call shape only.
    assert isinstance(signals, list)
    for s in signals:
        assert hasattr(s, "symbol") and hasattr(s, "direction") and hasattr(s, "strength")
        assert 0 <= s.strength <= 1.0
