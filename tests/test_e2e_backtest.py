"""End-to-end backtest smoke test (no DB / no MLflow)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

from aqp.data.ingestion import write_parquet


@pytest.fixture
def parquet_lake(tmp_path: Path, synthetic_bars: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> Path:
    df = synthetic_bars.rename(columns={"vt_symbol": "vt_symbol"}).copy()
    df["vt_symbol"] = df["vt_symbol"].str.replace(".NASDAQ", ".NASDAQ", regex=False)
    write_parquet(df, parquet_dir=tmp_path, overwrite=True)
    from aqp import config as cfg

    monkeypatch.setattr(cfg.settings, "parquet_dir", tmp_path, raising=False)
    # Reset the DuckDB connection that may have been cached
    if "aqp.data.duckdb_engine" in sys.modules:
        del sys.modules["aqp.data.duckdb_engine"]
    return tmp_path


def test_backtest_from_yaml_runs(parquet_lake: Path) -> None:
    cfg = yaml.safe_load(
        """
        strategy:
          class: FrameworkAlgorithm
          module_path: aqp.strategies.framework
          kwargs:
            universe_model:
              class: StaticUniverse
              module_path: aqp.strategies.universes
              kwargs: {symbols: [AAA, BBB, CCC]}
            alpha_model:
              class: MeanReversionAlpha
              module_path: aqp.strategies.mean_reversion
              kwargs: {lookback: 10, z_threshold: 1.0}
            portfolio_model:
              class: EqualWeightPortfolio
              module_path: aqp.strategies.portfolio
              kwargs: {max_positions: 3}
            risk_model:
              class: BasicRiskModel
              module_path: aqp.strategies.risk_models
              kwargs: {max_position_pct: 0.4, max_drawdown_pct: 0.5}
            execution_model:
              class: MarketOrderExecution
              module_path: aqp.strategies.execution
              kwargs: {}
            rebalance_every: 5
        backtest:
          class: EventDrivenBacktester
          module_path: aqp.backtest.engine
          kwargs:
            initial_cash: 50000.0
            commission_pct: 0.0005
            slippage_bps: 1.0
            start: "2022-01-01"
            end: "2023-06-30"
        """
    )
    from aqp.backtest.runner import run_backtest_from_config

    result = run_backtest_from_config(cfg, run_name="e2e-test", persist=False, mlflow_log=False)
    assert "sharpe" in result
    assert "total_return" in result
    assert result["final_equity"] is not None
