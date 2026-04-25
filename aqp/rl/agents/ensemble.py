"""FinRL ensemble agent — train A2C, PPO, DDPG; pick the best per window.

Implements the FinRL ICAIF 2020 "Ensemble Strategy":

1. On every walk-forward step, retrain each member on the same training
   window.
2. Evaluate every member on a held-out validation window.
3. Pick the member with the highest validation Sharpe (ties broken by
   final portfolio value).
4. Apply the winner's policy on the test window.

The implementation here is a thin façade over three
:class:`aqp.rl.agents.sb3_adapter.SB3Adapter` instances so we keep the
existing training / persistence / eval plumbing.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from aqp.rl.agents.sb3_adapter import SB3Adapter

logger = logging.getLogger(__name__)


@dataclass
class EnsembleMember:
    """One algo in the ensemble."""

    name: str
    algo: str
    policy: str = "MlpPolicy"
    algo_kwargs: dict[str, Any] | None = None


def _val_sharpe(history: list[float]) -> float:
    arr = np.asarray(history, dtype=float)
    if len(arr) < 2 or arr.std() == 0:
        return 0.0
    rets = np.diff(arr) / np.where(arr[:-1] == 0, 1.0, arr[:-1])
    if rets.std() == 0:
        return 0.0
    return float(math.sqrt(252) * rets.mean() / rets.std())


class EnsembleAgent:
    """Train + validate each SB3 member and hold the winner's policy."""

    def __init__(
        self,
        members: list[EnsembleMember] | None = None,
        total_timesteps: int = 100_000,
        validation_steps: int = 1_000,
    ) -> None:
        self.members = members or [
            EnsembleMember(name="a2c", algo="a2c"),
            EnsembleMember(name="ppo", algo="ppo"),
            EnsembleMember(name="ddpg", algo="ddpg"),
        ]
        self.total_timesteps = int(total_timesteps)
        self.validation_steps = int(validation_steps)
        self.best: SB3Adapter | None = None
        self.best_name: str = ""
        self.history: dict[str, list[float]] = {}
        self.scores: dict[str, float] = {}

    def train(self, train_env, val_env=None) -> "EnsembleAgent":
        """Train every member; pick the best on ``val_env`` (or train if None)."""
        eval_env = val_env or train_env
        for member in self.members:
            logger.info("EnsembleAgent: training %s", member.name)
            adapter = SB3Adapter(
                algo=member.algo,
                policy=member.policy,
                algo_kwargs=member.algo_kwargs or {},
            )
            adapter.build(train_env)
            adapter.train(total_timesteps=self.total_timesteps)
            history = self._rollout(adapter, eval_env)
            self.history[member.name] = history
            sharpe = _val_sharpe(history)
            self.scores[member.name] = sharpe
            logger.info("EnsembleAgent: %s validation Sharpe=%.3f", member.name, sharpe)
            if self.best is None or sharpe > self.scores[self.best_name]:
                self.best = adapter
                self.best_name = member.name
        return self

    def predict(self, observation, deterministic: bool = True):
        if self.best is None:
            raise RuntimeError("EnsembleAgent must be trained before predict().")
        return self.best.model.predict(observation, deterministic=deterministic)  # type: ignore[union-attr]

    def save(self, path: Path | str) -> None:
        if self.best is None:
            raise RuntimeError("No winning member to save.")
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.best.save(path / "best.zip")

    @classmethod
    def load(cls, path: Path | str, algo: str) -> "EnsembleAgent":
        agent = cls()
        agent.best = SB3Adapter(algo=algo)
        agent.best.load(Path(path) / "best.zip")
        return agent

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rollout(self, adapter: SB3Adapter, env) -> list[float]:
        obs, _ = env.reset()
        history: list[float] = []
        for _ in range(self.validation_steps):
            action, _ = adapter.model.predict(obs, deterministic=True)  # type: ignore[union-attr]
            obs, _reward, terminated, truncated, info = env.step(action)
            pv = info.get("portfolio_value")
            if pv is not None:
                history.append(float(pv))
            if bool(terminated) or bool(truncated):
                break
        return history
