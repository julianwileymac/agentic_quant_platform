"""``RegimeStratifiedEvaluation`` experiment tests."""
from __future__ import annotations

import numpy as np
import pytest

from aqp_rl.core.base import RL_KIND_EXPERIMENT, list_rl_components
from aqp_rl.experiments.regime_stratified import RegimeStratifiedEvaluation


class _FakeAgent:
    """Test double — emits a constant action."""

    def predict(self, obs, *, deterministic=True):  # noqa: D401
        return np.asarray([0.0], dtype=np.float32), None


class _FakeEnv:
    """Synthetic 10-step env that emits a regime label every step."""

    def __init__(self, labels: list[int]) -> None:
        self.labels = labels
        self.step_idx = 0
        # Minimal gym-like attribute surface.

        class _Box:
            shape = (1,)

            def sample(self):  # pragma: no cover
                return np.zeros(1, dtype=np.float32)

        class _Space:
            shape = (1,)

            def sample(self):  # pragma: no cover
                return np.zeros(1, dtype=np.float32)

        self.action_space = _Space()
        self.observation_space = _Box()

    def reset(self):
        self.step_idx = 0
        return np.zeros(1, dtype=np.float32), {
            "portfolio_value": 100.0,
            "nav_return": 0.0,
            "regime_label": self.labels[0],
        }

    def step(self, action):
        self.step_idx += 1
        idx = min(self.step_idx, len(self.labels) - 1)
        label = self.labels[idx]
        # Returns alternate up/down to give regime-specific signal.
        nav_return = 0.01 if label == 0 else -0.005
        reward = nav_return
        terminated = self.step_idx >= len(self.labels) - 1
        info = {
            "portfolio_value": 100.0 * (1 + nav_return * self.step_idx),
            "nav_return": nav_return,
            "regime_label": label,
        }
        return np.zeros(1, dtype=np.float32), reward, terminated, False, info


def test_registered_via_metaclass():
    registry = list_rl_components(RL_KIND_EXPERIMENT)
    assert "regime_stratified" in registry
    assert registry["regime_stratified"] is RegimeStratifiedEvaluation


def test_per_regime_metrics_produced():
    """Run a synthetic episode with two regimes and verify per-regime breakdown."""
    labels = [0] * 5 + [1] * 5
    env = _FakeEnv(labels)
    exp = RegimeStratifiedEvaluation(n_regimes=2)
    result = exp.run(agent=_FakeAgent(), env=env)
    assert "per_regime" in result
    assert "overall" in result
    assert 0 in result["per_regime"]
    assert 1 in result["per_regime"]
    # Regime 0 gets positive returns, regime 1 gets negative.
    assert result["per_regime"][0]["mean_return"] > 0
    assert result["per_regime"][1]["mean_return"] < 0
    # Overall steps tracked.
    assert result["n_steps"] >= 9


def test_uses_precomputed_labels_when_provided():
    """``regime_labels=[...]`` overrides the env's ``info['regime_label']``."""
    labels_env = [0] * 10
    env = _FakeEnv(labels_env)
    exp = RegimeStratifiedEvaluation(
        n_regimes=3,
        regime_labels=[2] * 10,  # force everything to regime 2
    )
    result = exp.run(agent=_FakeAgent(), env=env)
    assert 2 in result["per_regime"]
    # Regime 0 and 1 should be empty (or absent).
    assert result["per_regime"][2]["count"] > 0


def test_invalid_n_regimes_raises():
    with pytest.raises(ValueError):
        RegimeStratifiedEvaluation(n_regimes=0)
    with pytest.raises(ValueError):
        RegimeStratifiedEvaluation(n_regimes=3, n_episodes=0)
