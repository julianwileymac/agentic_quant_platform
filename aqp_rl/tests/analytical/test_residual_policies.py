"""``AlmgrenChrissResidualPolicy`` + ``AvellanedaStoikovResidualPolicy`` tests.

Verifies the residual-policy pattern:

- ``α`` linearly anneals from ``alpha_start`` to ``alpha_end`` over
  ``alpha_warmup`` steps.
- At ``α = 0`` the composite action equals the analytical baseline.
- At ``α = 1`` the composite action equals the underlying policy's
  emission (modulo clipping).
- :class:`AlmgrenChrissResidualPolicy` clips the composite trade to
  ``[0, q_remaining]`` so a noisy residual cannot overshoot the
  liquidation block.
- Both policies register through the :class:`RLComponent` metaclass.
- Both pass through :meth:`build`, :meth:`train`, :meth:`save`,
  :meth:`load` to the underlying base policy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import pytest

from aqp_rl.agents.almgren_chriss_residual import AlmgrenChrissResidualPolicy
from aqp_rl.agents.avellaneda_stoikov_residual import (
    AvellanedaStoikovResidualPolicy,
)
from aqp_rl.analytical.almgren_chriss import AlmgrenChrissParams
from aqp_rl.core.base import RL_KIND_AGENT, list_rl_components
from aqp_rl.core.policy import BaseRLAgent


class _FakeBasePolicy(BaseRLAgent):
    """Test double — emits a constant action vector."""

    rl_alias: ClassVar[str] = "_fake_base_policy_for_residual_tests"
    rl_kind: ClassVar[str] = "rl_agent"

    algorithm: str = "fake"

    def __init__(self, *, action: list[float] | None = None) -> None:
        self._action = np.asarray(action or [0.0], dtype=np.float32)
        self._built = False
        self._trained_steps = 0
        self._saved_path: Path | None = None
        self._loaded_path: Path | None = None

    def build(self, env: gym.Env) -> None:
        self._built = True

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        self._trained_steps += int(total_timesteps)

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        return self._action.copy(), None

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        self._saved_path = p
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        self._loaded_path = Path(path)


# --------------------------------------------------------------------------- AC residual


def test_ac_residual_registered():
    registry = list_rl_components(RL_KIND_AGENT)
    assert "almgren_chriss_residual" in registry
    assert registry["almgren_chriss_residual"] is AlmgrenChrissResidualPolicy


def test_ac_residual_alpha_zero_matches_analytical_baseline():
    """α=0 ⇒ composite trade equals the AC schedule (clipped to inventory)."""
    base = _FakeBasePolicy(action=[1e6])  # huge residual
    params = AlmgrenChrissParams()
    policy = AlmgrenChrissResidualPolicy(
        base_policy=base,
        ac_params=params,
        alpha_start=0.0,
        alpha_end=0.0,
        alpha_warmup=0,
    )
    nominal_first_trade = float(policy.schedule.trades[0])
    composite, _ = policy.predict({"step_idx": 0}, deterministic=True)
    assert composite[0] == pytest.approx(nominal_first_trade, rel=1e-6)


def test_ac_residual_alpha_one_adds_full_deviation_clipped():
    """α=1 + huge residual ⇒ clipped to inventory ceiling (q_remaining)."""
    base = _FakeBasePolicy(action=[1e9])  # huge positive residual
    params = AlmgrenChrissParams()
    policy = AlmgrenChrissResidualPolicy(
        base_policy=base,
        ac_params=params,
        alpha_start=1.0,
        alpha_end=1.0,
        clip_to_inventory=True,
    )
    q_remaining = float(policy.schedule.positions[0])
    composite, _ = policy.predict({"step_idx": 0}, deterministic=True)
    assert composite[0] == pytest.approx(q_remaining, rel=1e-6)


def test_ac_residual_alpha_anneal_linear():
    """α scales linearly from alpha_start → alpha_end over alpha_warmup."""
    base = _FakeBasePolicy(action=[0.0])
    policy = AlmgrenChrissResidualPolicy(
        base_policy=base,
        ac_params=AlmgrenChrissParams(),
        alpha_start=0.0,
        alpha_end=1.0,
        alpha_warmup=10,
    )
    alphas = [policy._alpha_at(t) for t in range(15)]  # noqa: SLF001
    assert alphas[0] == 0.0
    assert alphas[5] == pytest.approx(0.5, rel=1e-9)
    assert alphas[10] == 1.0
    # Plateau after warmup
    assert alphas[14] == 1.0


def test_ac_residual_lifecycle_delegates_to_base():
    base = _FakeBasePolicy(action=[0.0])
    policy = AlmgrenChrissResidualPolicy(base_policy=base)
    env = gym.make("CartPole-v1")
    policy.build(env)
    assert base._built  # noqa: SLF001
    policy.train(total_timesteps=42)
    assert base._trained_steps == 42  # noqa: SLF001
    p = Path("/tmp/x")
    policy.save(p)
    assert base._saved_path == p  # noqa: SLF001
    policy.load(p)
    assert base._loaded_path == p  # noqa: SLF001


def test_ac_residual_invalid_alpha_raises():
    base = _FakeBasePolicy(action=[0.0])
    with pytest.raises(ValueError):
        AlmgrenChrissResidualPolicy(base_policy=base, alpha_start=-0.1)
    with pytest.raises(ValueError):
        AlmgrenChrissResidualPolicy(base_policy=base, alpha_end=1.5)
    with pytest.raises(ValueError):
        AlmgrenChrissResidualPolicy(base_policy=base, alpha_warmup=-1)


def test_ac_residual_reset_zeros_step_counter():
    base = _FakeBasePolicy(action=[0.0])
    policy = AlmgrenChrissResidualPolicy(base_policy=base, alpha_warmup=100)
    for _ in range(50):
        policy.predict({"step_idx": 0}, deterministic=True)
    assert policy._steps_seen == 50  # noqa: SLF001
    policy.reset()
    assert policy._steps_seen == 0  # noqa: SLF001


# --------------------------------------------------------------------------- AS residual


def test_as_residual_registered():
    registry = list_rl_components(RL_KIND_AGENT)
    assert "avellaneda_stoikov_residual" in registry
    assert registry["avellaneda_stoikov_residual"] is AvellanedaStoikovResidualPolicy


def test_as_residual_alpha_zero_emits_baseline_multipliers():
    """α=0 ⇒ composite (spread, skew) multipliers = 1.0 (the AS baseline)."""
    base = _FakeBasePolicy(action=[10.0, -10.0])  # huge deviation
    policy = AvellanedaStoikovResidualPolicy(
        base_policy=base,
        alpha_start=0.0,
        alpha_end=0.0,
    )
    composite, _ = policy.predict(np.zeros(6, dtype=np.float32), deterministic=True)
    assert composite.shape == (2,)
    assert composite[0] == pytest.approx(1.0)
    assert composite[1] == pytest.approx(1.0)


def test_as_residual_clip_bounds_apply():
    base = _FakeBasePolicy(action=[1000.0, -1000.0])
    policy = AvellanedaStoikovResidualPolicy(
        base_policy=base,
        alpha_start=1.0,
        alpha_end=1.0,
        clip_low=0.0,
        clip_high=2.0,
    )
    composite, _ = policy.predict(np.zeros(6, dtype=np.float32), deterministic=True)
    assert composite[0] == pytest.approx(2.0)  # clipped from 1 + 1000
    assert composite[1] == pytest.approx(0.0)  # clipped from 1 - 1000


def test_as_residual_short_action_padded():
    """Base emits a 1-vector ⇒ padded to 2 with zero deviation."""
    base = _FakeBasePolicy(action=[0.5])
    policy = AvellanedaStoikovResidualPolicy(
        base_policy=base,
        alpha_start=1.0,
        alpha_end=1.0,
    )
    composite, _ = policy.predict(np.zeros(6, dtype=np.float32), deterministic=True)
    assert composite[0] == pytest.approx(1.5)
    assert composite[1] == pytest.approx(1.0)


def test_as_residual_invalid_clip_raises():
    base = _FakeBasePolicy(action=[0.0, 0.0])
    with pytest.raises(ValueError):
        AvellanedaStoikovResidualPolicy(
            base_policy=base,
            clip_low=2.0,
            clip_high=1.0,
        )


def test_as_residual_reset_zeros_step_counter():
    base = _FakeBasePolicy(action=[0.0, 0.0])
    policy = AvellanedaStoikovResidualPolicy(
        base_policy=base,
        alpha_warmup=100,
    )
    for _ in range(50):
        policy.predict(np.zeros(6, dtype=np.float32), deterministic=True)
    assert policy._steps_seen == 50  # noqa: SLF001
    policy.reset()
    assert policy._steps_seen == 0  # noqa: SLF001
