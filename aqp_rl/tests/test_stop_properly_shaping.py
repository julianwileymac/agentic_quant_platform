"""Hermetic tests for :class:`StopProperlyWrapper`."""
from __future__ import annotations

import pytest

from aqp_rl.core.reward import CompositeReward
from aqp_rl.rewards import PnLTerm, StopProperlyWrapper


@pytest.mark.parametrize("coef", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_truncated_reward_scales_by_coef(coef):
    # PnLTerm default scale=1e-4 so 500 PV delta -> 0.05 raw reward.
    inner = CompositeReward(terms=[PnLTerm(weight=1.0, scale=1.0)])
    wrapper = StopProperlyWrapper(inner=inner, coef=coef)
    state = {"portfolio_value": 100_000.0}
    next_state = {"portfolio_value": 100_500.0}
    info = {"truncated": True}
    shaped = wrapper.compute(state, None, next_state, info)
    raw = 500.0  # PnLTerm = (next.pv - prev.pv) * 1.0 = 500
    assert abs(shaped - raw * coef) < 1e-6
    # Original reward must be stashed on info for telemetry.
    assert info["stop_properly_original_reward"] == raw
    assert info["stop_properly_coef"] == coef


def test_no_op_when_not_truncated():
    inner = CompositeReward(terms=[PnLTerm(weight=1.0, scale=1.0)])
    wrapper = StopProperlyWrapper(inner=inner, coef=0.0)
    state = {"portfolio_value": 100_000.0}
    next_state = {"portfolio_value": 100_500.0}
    info = {}
    shaped = wrapper.compute(state, None, next_state, info)
    assert shaped == 500.0
    assert "stop_properly_original_reward" not in info


def test_decomposition_scales_per_term():
    inner = CompositeReward(terms=[PnLTerm(weight=1.0, scale=1.0)])
    wrapper = StopProperlyWrapper(inner=inner, coef=0.5)
    state = {"portfolio_value": 100_000.0}
    next_state = {"portfolio_value": 100_400.0}
    info = {"truncated": True}
    wrapper.compute(state, None, next_state, info)
    decomp = wrapper.decomposition(state, None, next_state, info)
    assert "pnl" in decomp
    assert abs(decomp["pnl"] - 200.0) < 1e-6  # 400 * 0.5


@pytest.mark.parametrize("invalid_coef", [-0.1, 1.1, 2.0])
def test_coef_validation_rejects_out_of_range(invalid_coef):
    inner = CompositeReward(terms=[PnLTerm()])
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        StopProperlyWrapper(inner=inner, coef=invalid_coef)


def test_wrapper_rejects_non_reward_model():
    with pytest.raises(TypeError, match="BaseRewardModel"):
        StopProperlyWrapper(inner="not a reward model", coef=0.5)


def test_truncating_terminations_carry_flag():
    """The three hard-breach terminations must flag truncates_episode=True."""
    from aqp_rl.terminations import (
        DrawdownTermination,
        HorizonTermination,
        MarginCallTermination,
        RiskBreachTermination,
    )
    assert DrawdownTermination.truncates_episode
    assert MarginCallTermination.truncates_episode
    assert RiskBreachTermination.truncates_episode
    # Horizon is the natural end — NOT a truncation.
    assert not HorizonTermination.truncates_episode
