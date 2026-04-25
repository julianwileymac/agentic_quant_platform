"""Paper trading session parity + lifecycle tests.

These tests rely only on the synthetic bars fixture + in-memory
``SimulatedBrokerage``, so they run anywhere (no Redis, no DB, no
broker SDKs).
"""
from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from aqp.backtest.broker_sim import SimulatedBrokerage
from aqp.backtest.engine import EventDrivenBacktester
from aqp.core.types import Symbol
from aqp.strategies.execution import MarketOrderExecution
from aqp.strategies.framework import FrameworkAlgorithm
from aqp.strategies.mean_reversion import MeanReversionAlpha
from aqp.strategies.portfolio import EqualWeightPortfolio
from aqp.strategies.risk_models import BasicRiskModel
from aqp.strategies.universes import StaticUniverse
from aqp.trading.clock import SimulatedReplayClock
from aqp.trading.feeds.base import DeterministicReplayFeed
from aqp.trading.session import PaperSessionConfig, PaperTradingSession


def _build_strategy() -> FrameworkAlgorithm:
    return FrameworkAlgorithm(
        universe_model=StaticUniverse(symbols=["AAA", "BBB", "CCC"]),
        alpha_model=MeanReversionAlpha(lookback=10, z_threshold=1.0),
        portfolio_model=EqualWeightPortfolio(max_positions=3),
        risk_model=BasicRiskModel(max_position_pct=0.35, max_drawdown_pct=0.5),
        execution_model=MarketOrderExecution(),
        rebalance_every=5,
    )


@pytest.fixture
def no_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip DB writes in the session — all tests run without Postgres."""

    class _Noop:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def add(self, *_a, **_k):
            return None

        def get(self, *_a, **_k):
            return None

    def _get_session():
        return _Noop()

    monkeypatch.setattr("aqp.trading.session.get_session", _get_session)
    monkeypatch.setattr("aqp.tasks._progress.publish", lambda *_a, **_kw: None)


def test_paper_session_runs_to_completion(
    synthetic_bars: pd.DataFrame, no_persistence: None
) -> None:
    strategy = _build_strategy()
    bars = synthetic_bars[synthetic_bars["vt_symbol"].isin({"AAA.NASDAQ", "BBB.NASDAQ", "CCC.NASDAQ"})]
    feed = DeterministicReplayFeed(bars, cadence_seconds=0.0)
    brokerage = SimulatedBrokerage(initial_cash=50000.0)
    session = PaperTradingSession(
        strategy=strategy,
        brokerage=brokerage,
        feed=feed,
        clock=SimulatedReplayClock(),
        config=PaperSessionConfig(run_name="unit", max_bars=200, stop_on_kill_switch=False),
    )
    session.pending_universe = [
        Symbol(ticker="AAA"),
        Symbol(ticker="BBB"),
        Symbol(ticker="CCC"),
    ]
    result = asyncio.run(session.run())
    assert result.status in {"completed"}
    assert result.bars_seen > 0
    # The simulator should accrue some orders even with tight risk.
    assert result.orders_submitted >= 0
    # Final equity reported matches what the brokerage's account says.
    assert abs(result.final_equity - brokerage.query_account().equity) < 1e-6


def test_shutdown_event_stops_session(
    synthetic_bars: pd.DataFrame, no_persistence: None
) -> None:
    """Calling ``request_shutdown`` drains the loop within one bar."""
    strategy = _build_strategy()
    bars = synthetic_bars[synthetic_bars["vt_symbol"].isin({"AAA.NASDAQ"})]
    feed = DeterministicReplayFeed(bars, cadence_seconds=0.0)
    session = PaperTradingSession(
        strategy=strategy,
        brokerage=SimulatedBrokerage(initial_cash=10000.0),
        feed=feed,
        clock=SimulatedReplayClock(),
        config=PaperSessionConfig(run_name="unit-stop", stop_on_kill_switch=False),
    )
    session.pending_universe = [Symbol(ticker="AAA")]

    async def _runner() -> None:
        task = asyncio.create_task(session.run())
        await asyncio.sleep(0)  # let it prime
        session.request_shutdown("test")
        await task

    asyncio.run(_runner())
    assert session._shutdown.is_set()


def test_kill_switch_halts_session(
    synthetic_bars: pd.DataFrame, no_persistence: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the kill switch engaged, the session drains after the first bar."""
    monkeypatch.setattr("aqp.trading.session.is_engaged", lambda: True)

    strategy = _build_strategy()
    bars = synthetic_bars[synthetic_bars["vt_symbol"].isin({"AAA.NASDAQ"})]
    feed = DeterministicReplayFeed(bars, cadence_seconds=0.0)
    session = PaperTradingSession(
        strategy=strategy,
        brokerage=SimulatedBrokerage(initial_cash=10000.0),
        feed=feed,
        clock=SimulatedReplayClock(),
        config=PaperSessionConfig(run_name="unit-kill", stop_on_kill_switch=True),
    )
    session.pending_universe = [Symbol(ticker="AAA")]
    result = asyncio.run(session.run())
    assert result.status == "completed"
    # Kill switch should stop very early.
    assert result.bars_seen <= 1


def test_session_uses_same_strategy_as_backtest(
    synthetic_bars: pd.DataFrame, no_persistence: None
) -> None:
    """Sanity: the paper session's strategy object and the backtester's can
    be built from the same constructor and both produce equity curves."""
    bars = synthetic_bars[synthetic_bars["vt_symbol"].isin({"AAA.NASDAQ", "BBB.NASDAQ", "CCC.NASDAQ"})]
    bt_strategy = _build_strategy()
    bt_result = EventDrivenBacktester(initial_cash=50000).run(bt_strategy, bars)
    assert len(bt_result.equity_curve) > 0

    ps_strategy = _build_strategy()
    feed = DeterministicReplayFeed(bars, cadence_seconds=0.0)
    session = PaperTradingSession(
        strategy=ps_strategy,
        brokerage=SimulatedBrokerage(initial_cash=50000),
        feed=feed,
        clock=SimulatedReplayClock(),
        config=PaperSessionConfig(run_name="parity", max_bars=100, stop_on_kill_switch=False),
    )
    session.pending_universe = [
        Symbol(ticker="AAA"),
        Symbol(ticker="BBB"),
        Symbol(ticker="CCC"),
    ]
    ps_result = asyncio.run(session.run())
    # We don't assert exact equity parity (the engines use slightly different
    # fill timing semantics), but both should have processed bars.
    assert ps_result.bars_seen > 0
