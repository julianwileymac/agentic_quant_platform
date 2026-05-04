"""Smoke tests for the vectorbt / backtesting.py engine adapters.

Both extras are optional — the test is skipped automatically when the
library isn't installed, so the default ``make test`` run stays green.
"""
from __future__ import annotations

import builtins

import pandas as pd
import pytest

from aqp.backtest.engine import BacktestResult
from aqp.core.registry import register
from aqp.strategies.examples.sma_cross import SmaCross


@pytest.fixture
def single_symbol_bars(synthetic_bars: pd.DataFrame) -> pd.DataFrame:
    return synthetic_bars[synthetic_bars["vt_symbol"] == "AAA.NASDAQ"].copy()


def test_vectorbt_engine_runs(single_symbol_bars: pd.DataFrame) -> None:
    pytest.importorskip("vectorbt")
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


def test_runner_engine_dispatch_event() -> None:
    """``_resolve_backtest_cfg`` should pick EventDrivenBacktester by default."""
    from aqp.backtest import runner

    cfg_event, label = runner._resolve_backtest_cfg({})
    assert label == "event"
    assert cfg_event["class"] == "EventDrivenBacktester"


def test_runner_engine_dispatch_shortcuts() -> None:
    from aqp.backtest import runner

    pro_cfg, pro_label = runner._resolve_backtest_cfg({"engine": "vectorbt-pro", "kwargs": {}})
    assert pro_label == "vectorbt-pro"
    assert pro_cfg["class"] == "VectorbtProEngine"

    vbt_cfg, vbt_label = runner._resolve_backtest_cfg({"engine": "vectorbt", "kwargs": {}})
    assert vbt_label == "vectorbt"
    assert vbt_cfg["class"] == "VectorbtEngine"

    bt_cfg, bt_label = runner._resolve_backtest_cfg({"engine": "bt", "kwargs": {}})
    assert bt_label == "backtesting"
    assert bt_cfg["class"] == "BacktestingPyEngine"

    fallback_cfg, fallback_label = runner._resolve_backtest_cfg(
        {"engine": "fallback", "primary": "vectorbt-pro", "fallbacks": ["event"]}
    )
    assert fallback_label == "fallback"
    assert fallback_cfg["class"] == "FallbackBacktestEngine"
    assert fallback_cfg["kwargs"]["primary"] == "vectorbt-pro"


def test_vectorbtpro_import_error_mentions_license(monkeypatch) -> None:
    from aqp.backtest.vectorbt_backend import VectorbtDependencyError, import_vectorbtpro

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "vectorbtpro":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(VectorbtDependencyError, match="licensed `vectorbtpro`"):
        import_vectorbtpro()


@register("FailingBacktestEngineForTest")
class FailingBacktestEngineForTest:
    def run(self, strategy, bars):
        raise RuntimeError("boom")


@register("PassingBacktestEngineForTest")
class PassingBacktestEngineForTest:
    def run(self, strategy, bars):
        equity = pd.Series([100.0, 101.0], index=pd.date_range("2024-01-01", periods=2))
        return BacktestResult(
            equity_curve=equity,
            trades=pd.DataFrame(),
            orders=pd.DataFrame(),
            summary={"engine": "passing"},
            initial_cash=100.0,
            final_equity=101.0,
        )


def test_fallback_engine_uses_next_engine(single_symbol_bars: pd.DataFrame) -> None:
    from aqp.backtest.fallback_engine import FallbackBacktestEngine

    engine = FallbackBacktestEngine(
        primary={"class": "FailingBacktestEngineForTest"},
        fallbacks=[{"class": "PassingBacktestEngineForTest"}],
    )
    result = engine.run(SmaCross(fast=5, slow=20), single_symbol_bars)
    assert result.summary["selected_engine"] == "passing"
    assert "FailingBacktestEngineForTest" in result.summary["fallback_errors"][0]
