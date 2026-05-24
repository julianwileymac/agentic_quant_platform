"""Thin adapter over Stable-Baselines3 — matches FinRL's ``DRLAgent`` surface.

Cleaned up + extended for the RL refactor:

- Accepts both ``algorithm`` (canonical) and ``algo`` (legacy) kwargs.
- Adds ``DQN`` (was advertised in the route but missing from the table).
- Adds optional ``sb3-contrib`` algos (``RecurrentPPO``, ``TRPO``,
  ``QRDQN``, ``MaskablePPO``) — silently skipped if the package is
  unavailable.
- Exposes ``.model`` (third-party object) **and** ``.policy`` (string
  policy id) consistently so legacy code that referenced either works.

Routes through :class:`aqp_rl.core.policy.BaseRLAgent`'s contract so the
runtime can drive it via a uniform ``build → train → save / load →
predict`` cycle.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym

from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


# ``stable_baselines3`` core algos.
_SB3_ALGOS = {
    "PPO": ("stable_baselines3", "PPO"),
    "A2C": ("stable_baselines3", "A2C"),
    "DDPG": ("stable_baselines3", "DDPG"),
    "SAC": ("stable_baselines3", "SAC"),
    "TD3": ("stable_baselines3", "TD3"),
    "DQN": ("stable_baselines3", "DQN"),
}

# Optional ``sb3-contrib`` algos.
_SB3_CONTRIB_ALGOS = {
    "RECURRENTPPO": ("sb3_contrib", "RecurrentPPO"),
    "TRPO": ("sb3_contrib", "TRPO"),
    "QRDQN": ("sb3_contrib", "QRDQN"),
    "MASKABLEPPO": ("sb3_contrib", "MaskablePPO"),
    "ARS": ("sb3_contrib", "ARS"),
    "TQC": ("sb3_contrib", "TQC"),
}

_ALGOS = {**_SB3_ALGOS, **_SB3_CONTRIB_ALGOS}


def _load_algo_class(name: str):
    key = name.upper().replace("-", "").replace("_", "")
    if key not in _ALGOS:
        raise KeyError(f"Unknown SB3 / sb3-contrib algorithm: {name!r}")
    mod_name, cls_name = _ALGOS[key]
    mod = importlib.import_module(mod_name)
    return getattr(mod, cls_name)


def list_supported_algorithms() -> list[str]:
    """Return the algorithms the adapter can build (filtered by what's installed)."""
    out: list[str] = []
    for key, (mod_name, _) in _ALGOS.items():
        try:
            importlib.import_module(mod_name)
            out.append(key)
        except Exception:  # noqa: BLE001
            continue
    return out


class SB3Adapter(BaseRLAgent):
    """Wraps an SB3 / sb3-contrib policy with the AQP training contract.

    Backwards-compat: also accepts ``algo=...`` (the legacy spelling) in
    addition to ``algorithm=...``.
    """

    rl_alias: ClassVar[str] = "SB3Adapter"
    rl_source: ClassVar[str] = "sb3"
    rl_category: ClassVar[str] = "drl"
    rl_tags: ClassVar[tuple[str, ...]] = ("sb3", "ppo", "a2c", "ddpg", "sac", "td3", "dqn")

    def __init__(
        self,
        algorithm: str | None = None,
        policy: str = "MlpPolicy",
        *,
        algo: str | None = None,
        **algo_kwargs: Any,
    ) -> None:
        # Accept either kwarg name (``algo`` was the legacy / FinRL spelling).
        chosen = algorithm or algo or "PPO"
        self.algorithm = str(chosen).upper()
        self.policy = str(policy)
        self.algo_kwargs = {k: v for k, v in algo_kwargs.items() if v is not None}
        self._cls = _load_algo_class(self.algorithm)
        self._model: Any | None = None

    def build(self, env: gym.Env) -> None:
        self._model = self._cls(self.policy, env, **self.algo_kwargs)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self._model is None:
            raise RuntimeError("SB3Adapter not built. Call .build(env) first.")
        self._model.learn(
            total_timesteps=int(total_timesteps),
            callback=callbacks or [],
            log_interval=int(log_interval),
            progress_bar=False,
        )

    def save(self, path: str | Path) -> Path:
        if self._model is None:
            raise RuntimeError("SB3Adapter has no model to save.")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._model.save(p.as_posix())
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        self._model = self._cls.load(str(path), env=env)

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        if self._model is None:
            raise RuntimeError("SB3Adapter has no model loaded.")
        return self._model.predict(obs, deterministic=deterministic)

    @property
    def model(self) -> Any:
        return self._model


__all__ = [
    "SB3Adapter",
    "list_supported_algorithms",
]
