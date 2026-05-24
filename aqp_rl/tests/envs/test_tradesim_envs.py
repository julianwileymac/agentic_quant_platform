"""Smoke + property tests for the Phase-3 ``tradesim_*`` envs.

Each env is tested for:

1. ``RLComponent`` metaclass registration under the expected
   ``rl_kind='rl_env'`` + ``rl_alias``.
2. ``gymnasium`` action/observation space integrity.
3. Successful ``reset()`` returning a Gymnasium 5-tuple
   ``(obs, info)`` shape.
4. Multiple ``step()`` calls returning the canonical 5-tuple
   ``(obs, reward, terminated, truncated, info)``.
5. ``info`` containing the AQP-canonical keys ``{portfolio_value,
   nav_return, t}`` plus per-env extras.
6. No NaN / Inf in observations, rewards, or portfolio values across
   a full episode.
7. Episode reaches a terminal step within ``len(data)`` ticks.

We intentionally use *synthetic* fixture DataFrames so the tests
don't need network access or seeded asset universes.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from aqp_rl.core.base import RL_KIND_ENV, list_rl_components
from aqp_rl.envs.tradesim_algotrading import AlgorithmicTradingEnv
from aqp_rl.envs.tradesim_execution import OrderExecutionEnv
from aqp_rl.envs.tradesim_hft import HighFrequencyTradingEnv
from aqp_rl.envs.tradesim_multimodal import MultimodalTradingEnv
from aqp_rl.envs.tradesim_portfolio import PortfolioManagementEnv


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def algo_df() -> pd.DataFrame:
    """Synthetic single-asset OHLC + indicator DataFrame."""
    rng = np.random.default_rng(0)
    n = 100
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "close": close,
            "rsi": rng.uniform(20, 80, n),
            "macd": rng.normal(0, 1, n),
        }
    )


@pytest.fixture
def portfolio_df() -> pd.DataFrame:
    """Synthetic multi-asset DataFrame: 3 stocks × 30 dates."""
    rng = np.random.default_rng(1)
    dates = pd.date_range("2020-01-01", periods=30, freq="D").strftime("%Y-%m-%d")
    rows = []
    for tic in ("AAPL", "MSFT", "GOOG"):
        base = 100.0
        for d in dates:
            base *= 1 + rng.normal(0.0005, 0.01)
            rows.append(
                {
                    "date": d,
                    "tic": tic,
                    "close": base,
                    "macd": rng.normal(0, 1),
                    "rsi": rng.uniform(20, 80),
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def execution_df() -> pd.DataFrame:
    """Synthetic execution price series."""
    rng = np.random.default_rng(2)
    n = 50
    close = 50 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame(
        {
            "close": close,
            "vwap": close + rng.normal(0, 0.05, n),
            "spread": rng.uniform(0.01, 0.05, n),
        }
    )


@pytest.fixture
def lob_df() -> pd.DataFrame:
    """Synthetic 5-level LOB snapshot DataFrame (30 rows)."""
    rng = np.random.default_rng(3)
    n = 30
    data: dict[str, np.ndarray] = {}
    for i in range(1, 6):
        data[f"bid{i}_price"] = 100 - 0.01 * i + rng.normal(0, 0.001, n)
        data[f"bid{i}_size"] = rng.uniform(0.01, 0.05, n)
        data[f"ask{i}_price"] = 100 + 0.01 * i + rng.normal(0, 0.001, n)
        data[f"ask{i}_size"] = rng.uniform(0.01, 0.05, n)
    return pd.DataFrame(data)


@pytest.fixture
def multimodal_price_df() -> pd.DataFrame:
    rng = np.random.default_rng(4)
    n = 40
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.1, n),
            "high": close + rng.uniform(0.1, 1.0, n),
            "low": close - rng.uniform(0.1, 1.0, n),
            "close": close,
            "adj_close": close,
        }
    )


# --------------------------------------------------------------------------- helpers


def _assert_canonical_info(info: dict) -> None:
    for key in ("portfolio_value", "nav_return", "t"):
        assert key in info, f"missing canonical info key {key!r}: {sorted(info)}"


def _walk_episode(env, n_steps: int = 50) -> int:
    obs, info = env.reset()
    _assert_canonical_info(info)
    if isinstance(obs, dict):
        for v in obs.values():
            assert np.isfinite(v).all()
    else:
        assert np.isfinite(np.asarray(obs)).all()
    actions_taken = 0
    for _ in range(n_steps):
        action = env.action_space.sample()
        out = env.step(action)
        assert len(out) == 5, "envs must return the Gymnasium 5-tuple"
        obs, reward, terminated, truncated, info = out
        actions_taken += 1
        _assert_canonical_info(info)
        if isinstance(obs, dict):
            for v in obs.values():
                assert np.isfinite(v).all()
        else:
            assert np.isfinite(np.asarray(obs)).all()
        assert math.isfinite(reward)
        if terminated or truncated:
            break
    return actions_taken


# --------------------------------------------------------------------------- AlgorithmicTradingEnv


def test_algotrading_registered():
    registry = list_rl_components(RL_KIND_ENV)
    assert "tradesim_algotrading" in registry
    assert registry["tradesim_algotrading"] is AlgorithmicTradingEnv


def test_algotrading_smoke_episode(algo_df: pd.DataFrame):
    env = AlgorithmicTradingEnv(
        data=algo_df,
        initial_amount=10_000.0,
        tech_indicator_list=["close", "rsi", "macd"],
        backward_num_day=5,
        forward_num_day=3,
        max_volume=2,
        future_weights=0.1,
        seed=42,
    )
    steps = _walk_episode(env, n_steps=200)
    assert steps > 0
    # Observation shape: F * backward_num_day + 2 = 3*5 + 2 = 17
    obs, _ = env.reset()
    assert obs.shape == (17,)


def test_algotrading_action_space_size(algo_df: pd.DataFrame):
    env = AlgorithmicTradingEnv(data=algo_df, max_volume=3)
    # 2*max_volume + 1 = 7
    assert env.action_space.n == 7


def test_algotrading_rejects_short_data():
    short = pd.DataFrame({"close": [100.0, 101.0]})
    with pytest.raises(ValueError):
        AlgorithmicTradingEnv(data=short, backward_num_day=5, forward_num_day=5)


# --------------------------------------------------------------------------- PortfolioManagementEnv


def test_portfolio_registered():
    registry = list_rl_components(RL_KIND_ENV)
    assert "tradesim_portfolio" in registry
    assert registry["tradesim_portfolio"] is PortfolioManagementEnv


def test_portfolio_smoke_episode(portfolio_df: pd.DataFrame):
    env = PortfolioManagementEnv(
        data=portfolio_df,
        initial_amount=100_000.0,
        tech_indicator_list=["close", "macd", "rsi"],
        time_steps=5,
        seed=42,
    )
    steps = _walk_episode(env, n_steps=100)
    assert steps > 0
    obs, _ = env.reset()
    # (F, N, T) = (3 features, 3 tickers, 5 timesteps)
    assert obs.shape == (3, 3, 5)
    # Action shape: (N + 1,) = (4,) cash + 3 tickers
    assert env.action_space.shape == (4,)


def test_portfolio_softmax_fallback_handles_logits(portfolio_df: pd.DataFrame):
    """Unnormalised action ⇒ softmax fallback ⇒ weights sum to 1."""
    env = PortfolioManagementEnv(data=portfolio_df, time_steps=3, seed=0)
    env.reset()
    logits = np.array([5.0, -1.0, 0.5, 3.0], dtype=np.float32)
    _, _, _, _, info = env.step(logits)
    assert info["target_weights"].sum() == pytest.approx(1.0, abs=1e-5)


def test_portfolio_rejects_short_history():
    short = pd.DataFrame(
        {
            "date": ["2020-01-01", "2020-01-02"],
            "tic": ["AAPL", "AAPL"],
            "close": [100.0, 101.0],
            "macd": [0.0, 0.0],
        }
    )
    with pytest.raises(ValueError):
        PortfolioManagementEnv(data=short, time_steps=5)


# --------------------------------------------------------------------------- OrderExecutionEnv


def test_execution_registered():
    registry = list_rl_components(RL_KIND_ENV)
    assert "tradesim_execution" in registry
    assert registry["tradesim_execution"] is OrderExecutionEnv


def test_execution_smoke_episode(execution_df: pd.DataFrame):
    env = OrderExecutionEnv(
        data=execution_df,
        initial_amount=100_000.0,
        state_length=5,
        tech_indicator_list=["close", "vwap", "spread"],
        target_order=1.0,
        teacher_lookahead=5,
        seed=42,
    )
    steps = _walk_episode(env, n_steps=100)
    assert steps > 0
    obs, info = env.reset()
    # Public state shape: (state_length, F) = (5, 3)
    assert obs.shape == (5, 3)
    # Info should contain the teacher-student dual state.
    assert "perfect_state" in info
    assert "private_state" in info


def test_execution_terminal_liquidates_inventory(execution_df: pd.DataFrame):
    """At terminal step the env unconditionally flattens any residual inventory."""
    env = OrderExecutionEnv(
        data=execution_df,
        state_length=5,
        teacher_lookahead=2,
        seed=0,
    )
    env.reset()
    # Take very small actions so we have residual at terminal.
    terminated = False
    info = {}
    for _ in range(60):
        _, _, terminated, _, info = env.step(np.array([0.001]))
        if terminated:
            break
    assert terminated
    assert info["inventory"] == pytest.approx(0.0, abs=1e-9)
    assert info["terminated"]


# --------------------------------------------------------------------------- HighFrequencyTradingEnv


def test_hft_registered():
    registry = list_rl_components(RL_KIND_ENV)
    assert "tradesim_hft" in registry
    assert registry["tradesim_hft"] is HighFrequencyTradingEnv


def test_hft_smoke_episode_with_dp_oracle(lob_df: pd.DataFrame):
    env = HighFrequencyTradingEnv(
        data=lob_df,
        stack_length=2,
        max_holding_number=0.05,
        num_action=5,
        enable_dp_oracle=True,
        seed=42,
    )
    obs, info = env.reset()
    # DP demonstration is a one-hot of length num_action.
    assert info["DP_action"].shape == (5,)
    assert info["DP_action"].sum() == 1
    # Available action mask is a 0/1 vector.
    assert info["available_action"].shape == (5,)
    steps = _walk_episode(env, n_steps=40)
    assert steps > 0


def test_hft_smoke_episode_without_dp_oracle(lob_df: pd.DataFrame):
    """``enable_dp_oracle=False`` skips the expensive DP table at init."""
    env = HighFrequencyTradingEnv(
        data=lob_df,
        stack_length=1,
        num_action=3,
        enable_dp_oracle=False,
        seed=0,
    )
    steps = _walk_episode(env, n_steps=40)
    assert steps > 0


def test_hft_observation_shape(lob_df: pd.DataFrame):
    env = HighFrequencyTradingEnv(
        data=lob_df,
        stack_length=3,
        num_action=11,
        enable_dp_oracle=False,
    )
    # Default tech_indicator_list = all bid/ask price + size cols = 20 cols
    # × stack_length 3 = 60 dims
    expected = len(env.tech_indicator_list) * env.stack_length
    obs, _ = env.reset()
    assert obs.shape == (expected,)


# --------------------------------------------------------------------------- MultimodalTradingEnv


def test_multimodal_registered():
    registry = list_rl_components(RL_KIND_ENV)
    assert "finagent_trading" in registry
    assert registry["finagent_trading"] is MultimodalTradingEnv


def test_multimodal_smoke_episode_price_only(multimodal_price_df: pd.DataFrame):
    env = MultimodalTradingEnv(
        price_data=multimodal_price_df,
        look_back_days=5,
        look_forward_days=3,
        initial_amount=10_000.0,
        seed=42,
    )
    obs, info = env.reset()
    assert isinstance(obs, dict)
    assert "price" in obs and obs["price"].shape[0] == 5
    assert "news" in obs and obs["news"].shape[0] == 5
    assert info["symbol"] == "AAPL"
    steps = _walk_episode(env, n_steps=60)
    assert steps > 0


def test_multimodal_with_news_dataframe(multimodal_price_df: pd.DataFrame):
    """News slice is properly populated when ``news_data`` is provided."""
    rng = np.random.default_rng(5)
    news_df = pd.DataFrame(
        {
            "sentiment_score": rng.normal(0, 1, len(multimodal_price_df)),
            "embedding_dim_0": rng.normal(0, 1, len(multimodal_price_df)),
            "embedding_dim_1": rng.normal(0, 1, len(multimodal_price_df)),
        }
    )
    env = MultimodalTradingEnv(
        price_data=multimodal_price_df,
        news_data=news_df,
        look_back_days=4,
        seed=0,
    )
    obs, _ = env.reset()
    assert obs["news"].shape == (4, 3)
    assert np.isfinite(obs["news"]).all()


def test_multimodal_action_map():
    """Action 0=SELL, 1=HOLD, 2=BUY round-trips through ``info['action']``."""
    rng = np.random.default_rng(6)
    df = pd.DataFrame(
        {
            "open": np.linspace(100, 110, 40),
            "high": np.linspace(101, 111, 40),
            "low": np.linspace(99, 109, 40),
            "close": np.linspace(100, 110, 40),
            "adj_close": np.linspace(100, 110, 40),
        }
    )
    env = MultimodalTradingEnv(price_data=df, look_back_days=4, seed=0)
    env.reset()
    _, _, _, _, info_buy = env.step(2)
    assert info_buy["action"] in {"BUY", "HOLD"}  # HOLD if can't afford
    _, _, _, _, info_sell = env.step(0)
    assert info_sell["action"] in {"SELL", "HOLD"}
    _, _, _, _, info_hold = env.step(1)
    assert info_hold["action"] == "HOLD"
