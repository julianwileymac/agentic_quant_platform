"""Smoke tests for the graduated MarketMakingEnv (Avellaneda-Stoikov)."""
from __future__ import annotations

import numpy as np
import pytest

# RL envs depend on gymnasium; skip the whole module when it's missing.
pytest.importorskip("gymnasium")

from aqp_rl.envs.lucic_tse_options_env import LucicTsePortfolioEnv  # noqa: E402
from aqp_rl.envs.market_making_env import (  # noqa: E402
    MarketMakingEnv,
    MarketMakingStubEnv,
)
from aqp_rl.envs.optimal_execution_env import OptimalExecutionEnv  # noqa: E402


def test_market_making_env_obs_shape() -> None:
    env = MarketMakingEnv(horizon=10, inventory_cap=20.0, seed=42)
    obs, info = env.reset(seed=42)
    assert obs.shape == (6,)
    assert "inventory" in info
    obs2, reward, terminated, truncated, info2 = env.step(np.array([1.0, 0.5]))
    assert obs2.shape == (6,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)


def test_market_making_env_terminates_on_horizon() -> None:
    env = MarketMakingEnv(horizon=3, inventory_cap=100.0, seed=42)
    env.reset(seed=42)
    last_terminated = False
    for _ in range(5):
        _, _, terminated, _, _ = env.step(np.array([0.5, 0.5]))
        last_terminated = last_terminated or terminated
    assert last_terminated


def test_market_making_stub_env_still_registers() -> None:
    env = MarketMakingStubEnv(horizon=10)
    obs, _ = env.reset()
    assert obs.shape == (4,)
    obs2, reward, _, _, _ = env.step(np.array([0.5, 0.5]))
    assert obs2.shape == (4,)
    assert isinstance(reward, float)


def test_optimal_execution_env_runs() -> None:
    env = OptimalExecutionEnv(horizon=20, initial_inventory=50.0, seed=42)
    obs, _ = env.reset(seed=42)
    assert obs.shape == (5,)
    total_reward = 0.0
    for _ in range(25):
        obs, reward, terminated, _, info = env.step(np.array([0.3]))
        total_reward += reward
        if terminated:
            break
    # Inventory must end at exactly zero (force-liquidation at horizon).
    assert abs(env.inventory) < 1e-6


def test_lucic_tse_env_runs_with_zero_action() -> None:
    env = LucicTsePortfolioEnv(horizon=5, n_strikes=3, n_expiries=2, seed=42)
    obs, _ = env.reset(seed=42)
    assert obs.shape == (7,)
    obs2, reward, terminated, _, info = env.step(np.array([1.0, 1.0]))
    assert obs2.shape == (7,)
    assert isinstance(reward, float)


def test_envs_registered() -> None:
    from aqp.core.registry import list_by_kind

    rl_envs = list_by_kind("rl_env")
    assert "MarketMakingEnv" in rl_envs
    assert "MarketMakingStubEnv" in rl_envs
    assert "OptimalExecutionEnv" in rl_envs
    assert "LucicTsePortfolioEnv" in rl_envs
    assert "MbtGymAdapterEnv" in rl_envs
