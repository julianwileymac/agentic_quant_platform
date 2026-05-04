"""End-to-end vbt-pro engine smoke test — skipped when vbt-pro absent."""
from __future__ import annotations

import pandas as pd
import pytest

vbt = pytest.importorskip("vectorbtpro")


def test_vbtpro_engine_signals_smoke(synthetic_bars: pd.DataFrame) -> None:
    from aqp.backtest.vbtpro.engine import VectorbtProEngine
    from aqp.strategies.examples.sma_cross import SmaCross

    engine = VectorbtProEngine(
        mode="signals",
        initial_cash=100_000.0,
        warmup_bars=20,
        allow_short=False,
        cash_sharing=True,
        group_by=True,
    )
    result = engine.run(SmaCross(fast=10, slow=30, allow_short=False), synthetic_bars)
    assert result.initial_cash == 100_000.0
    assert len(result.equity_curve) > 0
    assert result.summary.get("engine") == "vectorbt-pro"
    assert result.summary.get("mode") == "signals"
    # vbt_* native stats should be merged into the summary.
    assert any(k.startswith("vbt_") for k in result.summary)


def test_vbtpro_engine_holding_baseline(synthetic_bars: pd.DataFrame) -> None:
    from aqp.backtest.vbtpro.engine import VectorbtProEngine

    engine = VectorbtProEngine(mode="holding", initial_cash=100_000.0)
    result = engine.run(strategy=None, bars=synthetic_bars)
    assert result.summary.get("mode") == "holding"
    assert len(result.equity_curve) > 0


def test_vbtpro_engine_random_baseline(synthetic_bars: pd.DataFrame) -> None:
    from aqp.backtest.vbtpro.engine import VectorbtProEngine

    engine = VectorbtProEngine(
        mode="random",
        initial_cash=100_000.0,
        random_kwargs={"n": 5, "seed": 7},
    )
    result = engine.run(strategy=None, bars=synthetic_bars)
    assert result.summary.get("mode") == "random"
