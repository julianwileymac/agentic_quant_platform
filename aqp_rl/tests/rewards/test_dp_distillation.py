"""DP-distillation reward (HFT pattern) — unit tests."""
from __future__ import annotations

import pytest

from aqp_rl.core.base import RL_KIND_REWARD, list_rl_components
from aqp_rl.rewards.dp_distillation import DPDistillation


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_REWARD)
    assert "dp_distillation" in registry
    assert registry["dp_distillation"] is DPDistillation


def test_zero_when_distribution_missing():
    term = DPDistillation()
    assert term.compute(state={}, action=None, next_state={}, info={}) == 0.0
    # Only one of the two missing.
    info_one = {"agent_action_distribution": [0.5, 0.5]}
    assert term.compute(state={}, action=None, next_state={}, info=info_one) == 0.0


def test_zero_when_distributions_match():
    """KL(p || p) = 0 ⇒ reward = 0."""
    term = DPDistillation(ada=1.0)
    info = {
        "agent_action_distribution": [0.25, 0.25, 0.25, 0.25],
        "DP_action": [0.25, 0.25, 0.25, 0.25],
    }
    out = term.compute(state={}, action=None, next_state={}, info=info)
    assert out == pytest.approx(0.0, abs=1e-6)


def test_negative_when_distributions_diverge():
    """Different distributions ⇒ KL > 0 ⇒ reward < 0."""
    term = DPDistillation(ada=1.0)
    info = {
        "agent_action_distribution": [0.7, 0.1, 0.1, 0.1],
        "DP_action": [0.1, 0.7, 0.1, 0.1],
    }
    out = term.compute(state={}, action=None, next_state={}, info=info)
    assert out < 0


def test_larger_ada_more_negative():
    info = {
        "agent_action_distribution": [0.9, 0.1],
        "DP_action": [0.1, 0.9],
    }
    out_small = DPDistillation(ada=0.1).compute(state={}, action=None, next_state={}, info=info)
    out_large = DPDistillation(ada=10.0).compute(state={}, action=None, next_state={}, info=info)
    assert out_large < out_small


def test_one_hot_dp_action_handled():
    """DP often emits one-hot demonstrations; we floor with eps to avoid log(0)."""
    term = DPDistillation(ada=1.0)
    info = {
        "agent_action_distribution": [0.5, 0.5],
        "DP_action": [1.0, 0.0],  # one-hot
    }
    out = term.compute(state={}, action=None, next_state={}, info=info)
    assert out < 0  # finite, negative
    assert out > -1e6  # not blown up by log(0)


def test_invalid_ada_raises():
    with pytest.raises(ValueError):
        DPDistillation(ada=-0.1)


def test_invalid_eps_raises():
    with pytest.raises(ValueError):
        DPDistillation(eps=0.0)


def test_unequal_length_distributions_yield_zero():
    """Mismatched length ⇒ skip silently (zero reward)."""
    term = DPDistillation()
    info = {
        "agent_action_distribution": [0.3, 0.3, 0.4],
        "DP_action": [0.5, 0.5],
    }
    assert term.compute(state={}, action=None, next_state={}, info=info) == 0.0


def test_accepts_numpy_arrays():
    """Numpy arrays are coerced via ``.tolist()``."""
    np = pytest.importorskip("numpy")
    term = DPDistillation(ada=1.0)
    info = {
        "agent_action_distribution": np.array([0.5, 0.5]),
        "DP_action": np.array([0.5, 0.5]),
    }
    out = term.compute(state={}, action=None, next_state={}, info=info)
    assert out == pytest.approx(0.0, abs=1e-6)
