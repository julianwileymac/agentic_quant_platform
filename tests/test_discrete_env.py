"""Tests for the discrete buy/sell/hold env."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("gymnasium", reason="gymnasium is an optional RL dep")
pytest.importorskip("stable_baselines3", reason="sb3 is imported transitively")

from aqp.rl.envs.stock_trading_discrete import StockTradingDiscreteEnv  # noqa: E402


@pytest.fixture
def _patch_load_bars(monkeypatch, synthetic_bars: pd.DataFrame) -> None:
    """Avoid hitting DuckDB / the real parquet lake."""

    def fake_load_bars(symbols, start, end, indicators=None):
        df = synthetic_bars.copy()
        df = df[df["vt_symbol"] == f"{symbols[0]}.NASDAQ"]
        for ind in indicators or []:
            if ind not in df.columns:
                df[ind] = 0.0
        return df.reset_index(drop=True)

    monkeypatch.setattr(
        "aqp.rl.envs.stock_trading_discrete.load_bars",
        fake_load_bars,
    )


def test_env_reset_returns_obs(_patch_load_bars) -> None:
    env = StockTradingDiscreteEnv("AAA", "2021-01-01", "2023-12-29", initial_balance=10000.0)
    obs, info = env.reset(seed=0)
    assert isinstance(obs, np.ndarray)
    assert obs.shape == env.observation_space.shape


def test_env_actions_change_state(_patch_load_bars) -> None:
    env = StockTradingDiscreteEnv(
        "AAA",
        "2021-01-01",
        "2023-12-29",
        initial_balance=10000.0,
        shares_per_trade=5,
    )
    env.reset(seed=0)

    # Buy: cash goes down, shares go up.
    _, reward_buy, done, _, info_buy = env.step(env.BUY)
    assert info_buy["shares"] == 5
    assert info_buy["cash"] < 10000.0
    assert not done

    # Hold: shares stay at 5.
    _, _, done, _, info_hold = env.step(env.HOLD)
    assert info_hold["shares"] == 5

    # Sell: shares drop back to zero.
    _, _, done, _, info_sell = env.step(env.SELL)
    assert info_sell["shares"] == 0
    assert info_sell["cash"] > info_buy["cash"]


def test_env_insufficient_cash_no_op(_patch_load_bars) -> None:
    env = StockTradingDiscreteEnv(
        "AAA",
        "2021-01-01",
        "2023-12-29",
        initial_balance=1.0,  # can't afford a buy
        shares_per_trade=10,
    )
    env.reset(seed=0)
    _, _, _, _, info = env.step(env.BUY)
    assert info["shares"] == 0
    assert info["cash"] == pytest.approx(1.0, rel=1e-6)
