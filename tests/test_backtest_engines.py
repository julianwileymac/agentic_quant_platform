"""Smoke tests for the vectorbt / backtesting.py engine adapters.

Both extras are optional — the test is skipped automatically when the
library isn't installed, so the default ``make test`` run stays green.
"""
from __future__ import annotations

import pandas as pd
import pytest

from aqp.strategies.examples.sma_cross import SmaCross


@pytest.fixture
def single_symbol_bars(synthetic_bars: pd.DataFrame) -> pd.DataFrame:
    return synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()


def test_vectorbt_engine_runs(single_symbol_bars: pd.DataFrame) -> None:
    vbt = pytest.importorskip("vectorbt")
    from aqp.backtest.vectorbt_engine import VectorbtEngine

    engine = VectorbtEngine(initial_cash=100_000.0, warmup_bars=30, allow_short=False)
    result = engine.run(SmaCross(fast=10, slow=20, allow_short=False), single_symbol_bars)
    assert result.initial_cash == 100_000.0
    assert len(result.equity_curve) > 0
    assert "engine" in result.summary and result.summary["engine"] == "vectorbt"


def test_backtesting_py_engine_runs(single_symbol_bars: pd.DataFrame) -> None:
    pytest.importorskip("backtesting")
    from aqp.backtest.bt_engine import BacktestingPyEngine

    engine = BacktestingPyEngine(cash=100_000.0, warmup_bars=30)
    result = engine.run(SmaCross(fast=5, slow=20, allow_short=True), single_symbol_bars)
    assert result.initial_cash == 100_000.0
    assert len(result.equity_curve) > 0
    assert result.summary.get("engine") == "backtesting"


def test_runner_engine_dispatch_event(synthetic_bars, monkeypatch) -> None:
    """``_resolve_backtest_cfg`` should pick EventDrivenBacktester by default."""
    from aqp.backtest import runner

    cfg_event, label = runner._resolve_backtest_cfg({})
    assert label == "event"
    assert cfg_event["class"] == "EventDrivenBacktester"


def test_runner_engine_dispatch_shortcuts() -> None:
    from aqp.backtest import runner

    vbt_cfg, vbt_label = runner._resolve_backtest_cfg({"engine": "vectorbt", "kwargs": {}})
    assert vbt_label == "vectorbt"
    assert vbt_cfg["class"] == "VectorbtEngine"

    bt_cfg, bt_label = runner._resolve_backtest_cfg({"engine": "bt", "kwargs": {}})
    assert bt_label == "backtesting"
    assert bt_cfg["class"] == "BacktestingPyEngine"
