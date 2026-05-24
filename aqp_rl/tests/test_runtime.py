"""Smoke test for :class:`aqp_rl.runtime.RLRuntime`.

Builds a tiny in-memory env / agent pair so we don't depend on any
external deps (mlflow / iceberg). The trajectory store is forced to
the in-memory implementation.
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
import pytest
from gymnasium import spaces

from aqp_rl.core.replay import InMemoryTrajectoryStore
from aqp_rl.runtime import RLRuntime
from aqp_rl.spec import RLExperimentSpec


class _ToyEnv(gym.Env):
    def __init__(self, *, horizon: int = 5) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.observation_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(2,), dtype=np.float32)
        self.history = [100.0]
        self.t = 0
        self.portfolio_value = 100.0

    def reset(self, *, seed: int | None = None, options: Any = None):  # type: ignore[override]
        super().reset(seed=seed)
        self.t = 0
        self.portfolio_value = 100.0
        self.history = [100.0]
        return np.zeros(2, dtype=np.float32), {}

    def step(self, action):  # type: ignore[override]
        self.t += 1
        delta = float(np.sum(np.asarray(action, dtype=np.float32)))
        self.portfolio_value += delta
        self.history.append(self.portfolio_value)
        terminated = self.t >= self.horizon - 1
        info = {"portfolio_value": self.portfolio_value}
        return np.full(2, delta, dtype=np.float32), float(delta), bool(terminated), False, info


class _ToyAgent:
    algorithm = "Toy"

    def build(self, env):
        self.env = env

    def train(self, total_timesteps, **_):
        self._steps = int(total_timesteps)

    def predict(self, obs, deterministic=True):
        return np.zeros_like(obs, dtype=np.float32), None

    def save(self, path):
        return path

    def load(self, path, env=None):
        self.env = env

    @property
    def model(self):
        return self


def test_runtime_train_runs_rollout(tmp_path, monkeypatch):
    spec = RLExperimentSpec.model_validate(
        {
            "name": "toy-rl-runtime",
            "env": {"class": "tests.rl.test_runtime._ToyEnv", "kwargs": {"horizon": 5}},
            "agent": {"class": "tests.rl.test_runtime._ToyAgent"},
            "training": {"total_timesteps": 10},
        }
    )
    runtime = RLRuntime(
        spec,
        trajectory_store=InMemoryTrajectoryStore(),
        persist_trajectories=False,
    )
    # Stub out DB / MLflow plumbing so the test doesn't require a running
    # Postgres or MLflow server (CI / hermetic).
    monkeypatch.setattr(runtime, "_snapshot_spec", lambda: (None, None))
    monkeypatch.setattr(runtime, "_open_run_row", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "_finalise_run_row", lambda *a, **k: None)
    monkeypatch.setattr(runtime, "_record_episode", lambda *a, **k: None)

    def _no_mlflow(self, *, env, agent, run_name):
        agent.train(total_timesteps=int(self.spec.training.total_timesteps))
        return None, None

    monkeypatch.setattr(RLRuntime, "_train_with_mlflow", _no_mlflow)

    result = runtime.train(run_name="toy")
    assert result.status == "completed"
