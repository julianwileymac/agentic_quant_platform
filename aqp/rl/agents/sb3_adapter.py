"""Thin adapter over Stable-Baselines3 — matches FinRL's ``DRLAgent`` surface."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import gymnasium as gym

from aqp.core.registry import register

logger = logging.getLogger(__name__)

_ALGOS = {
    "PPO": ("stable_baselines3", "PPO"),
    "A2C": ("stable_baselines3", "A2C"),
    "DDPG": ("stable_baselines3", "DDPG"),
    "SAC": ("stable_baselines3", "SAC"),
    "TD3": ("stable_baselines3", "TD3"),
}


def _load_algo_class(name: str):
    mod_name, cls_name = _ALGOS[name.upper()]
    import importlib

    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)


@register("SB3Adapter")
class SB3Adapter:
    """Wraps an SB3 policy with the training hooks our trainer expects."""

    def __init__(
        self,
        algorithm: str = "PPO",
        policy: str = "MlpPolicy",
        **algo_kwargs: Any,
    ) -> None:
        self.algorithm = algorithm.upper()
        self.policy = policy
        self.algo_kwargs = {k: v for k, v in algo_kwargs.items() if v is not None}
        self._model: Any | None = None
        self._cls = _load_algo_class(self.algorithm)

    def build(self, env: gym.Env) -> None:
        self._model = self._cls(self.policy, env, **self.algo_kwargs)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self._model is None:
            raise RuntimeError("Adapter not built. Call .build(env) first.")
        self._model.learn(
            total_timesteps=total_timesteps,
            callback=callbacks or [],
            log_interval=log_interval,
            progress_bar=False,
        )

    def save(self, path: str | Path) -> Path:
        if self._model is None:
            raise RuntimeError("Nothing to save.")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._model.save(p.as_posix())
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        self._model = self._cls.load(str(path), env=env)

    def predict(self, obs, deterministic: bool = True):
        if self._model is None:
            raise RuntimeError("Nothing loaded.")
        return self._model.predict(obs, deterministic=deterministic)

    @property
    def model(self) -> Any:
        return self._model
