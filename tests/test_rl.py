"""Smoke tests for the RL env (bypasses network — writes synthetic parquet)."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd
import pytest

from aqp.data.ingestion import write_parquet


@pytest.fixture
def parquet_lake(tmp_path: Path, synthetic_bars: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Write synthetic parquet and re-point the settings.parquet_dir
    write_parquet(synthetic_bars, parquet_dir=tmp_path, overwrite=True)
    from aqp import config as cfg

    monkeypatch.setattr(cfg.settings, "parquet_dir", tmp_path, raising=False)
    # Force a fresh DuckDB connection
    if "aqp.data.duckdb_engine" in sys.modules:
        importlib.reload(sys.modules["aqp.data.duckdb_engine"])
    return tmp_path


def test_stock_trading_env_reset_step(parquet_lake: Path) -> None:
    from aqp.rl.envs.stock_trading_env import StockTradingEnv

    env = StockTradingEnv(
        symbols=["AAA", "BBB"],
        start="2021-01-15",
        end="2023-12-01",
        indicators=["sma_20", "rsi_14"],
    )
    obs, _ = env.reset(seed=0)
    assert obs.shape[0] == env.observation_space.shape[0]
    obs, r, done, trunc, info = env.step(env.action_space.sample())
    assert obs.shape[0] == env.observation_space.shape[0]
    assert isinstance(r, float)
    assert "portfolio_value" in info


def test_sb3_adapter_builds(parquet_lake: Path) -> None:
    pytest.importorskip("stable_baselines3")
    from aqp.rl.agents.sb3_adapter import SB3Adapter
    from aqp.rl.envs.stock_trading_env import StockTradingEnv

    env = StockTradingEnv(
        symbols=["AAA", "BBB"],
        start="2021-01-15",
        end="2023-12-01",
        indicators=["sma_20"],
    )
    adapter = SB3Adapter(algorithm="PPO", policy="MlpPolicy", n_steps=64, batch_size=32)
    adapter.build(env)
    assert adapter.model is not None
