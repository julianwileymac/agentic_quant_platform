"""Hermetic tests for :class:`ReinforcePlusPlusAdvantage`.

Tests the FinRL-X port of NeMo-RL's leave-one-out cohort baseline +
decoupled global normalisation. Pure-numpy — no live DB, no Redis,
no network.
"""
from __future__ import annotations

import numpy as np
import pytest

from aqp.rl.advantage import (
    GAEAdvantage,
    GRPOAdvantage,
    ReinforcePlusPlusAdvantage,
)


def test_reinforce_plus_plus_zero_centered_per_cohort():
    """LOO baselines must produce per-cohort centered rewards summing to 0."""
    est = ReinforcePlusPlusAdvantage(
        minus_baseline=True, global_normalization=True, leave_one_out=True
    )
    rewards = np.array([1.0, -0.5, 2.0, 0.3, 0.1, -0.2, 0.8, 1.2], dtype=np.float64)
    group_ids = np.array([0, 0, 0, 0, 1, 1, 1, 1], dtype=np.int64)
    out = est.compute(rewards=rewards, group_ids=group_ids)
    centered_g0 = rewards[:4] - out.baselines[:4]
    centered_g1 = rewards[4:] - out.baselines[4:]
    assert abs(centered_g0.sum()) < 1e-9
    assert abs(centered_g1.sum()) < 1e-9
    assert out.extras["num_groups"] == 2


def test_minus_baseline_false_returns_raw_rewards_scaled():
    """``minus_baseline=False`` leaves the reward signal intact."""
    est = ReinforcePlusPlusAdvantage(minus_baseline=False, global_normalization=True)
    rewards = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    out = est.compute(rewards=rewards, group_ids=np.zeros(4, dtype=np.int64))
    # Without centering, the advantages should preserve the rank of rewards.
    assert np.all(np.argsort(out.advantages) == np.argsort(rewards))


def test_truncated_rewards_recorded_in_extras():
    est = ReinforcePlusPlusAdvantage()
    rewards = np.array([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    truncated = np.array([0, 1, 0, 1], dtype=bool)
    out = est.compute(rewards=rewards, truncated=truncated)
    assert out.extras["truncation_rate"] == 0.5


def test_grpo_uniform_cohort_baselines():
    est = GRPOAdvantage(normalise_by_cohort_std=True)
    rewards = np.array([1.0, -0.5, 2.0, 0.3], dtype=np.float64)
    out = est.compute(rewards=rewards, group_ids=np.zeros(4, dtype=np.int64))
    assert np.allclose(out.baselines, rewards.mean())


def test_grpo_unstable_when_single_cohort_unit_variance():
    """Single-cohort with constant rewards collapses to zero advantage."""
    est = GRPOAdvantage()
    rewards = np.ones(4, dtype=np.float64)
    out = est.compute(rewards=rewards, group_ids=np.zeros(4, dtype=np.int64))
    # With identical rewards the centered values are all 0; advantage = 0.
    assert np.allclose(out.advantages, 0.0)


def test_gae_requires_values():
    est = GAEAdvantage()
    with pytest.raises(ValueError, match="values"):
        est.compute(rewards=np.array([0.1, 0.2], dtype=np.float64))


def test_gae_terminal_bootstrap_correct():
    """With dones=[0,0,0,1] and zero values, GAE returns the discounted rewards."""
    est = GAEAdvantage(gamma=0.9, lam=1.0, normalise=False)
    rewards = np.array([0.1, 0.1, 0.1, 0.1], dtype=np.float64)
    values = np.zeros(4, dtype=np.float64)
    dones = np.array([0, 0, 0, 1], dtype=np.float64)
    out = est.compute(rewards=rewards, values=values, dones=dones)
    # With lam=1.0 GAE collapses to discounted Monte-Carlo returns.
    expected_last_adv = 0.1
    assert abs(out.advantages[-1] - expected_last_adv) < 1e-9


def test_empty_input_returns_empty_arrays():
    est = ReinforcePlusPlusAdvantage()
    out = est.compute(rewards=np.zeros(0, dtype=np.float64))
    assert out.advantages.shape == (0,)
    assert out.returns.shape == (0,)


def test_rl_kind_registered():
    """All three estimators must register under rl_advantage_estimator kind."""
    from aqp.rl.core.base import RL_KIND_ADVANTAGE, list_rl_components

    components = list_rl_components(kind=RL_KIND_ADVANTAGE)
    assert "ReinforcePlusPlus" in components
    assert "GRPO" in components
    assert "GAE" in components
