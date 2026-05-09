"""Thin adapter over `Ray RLlib <https://docs.ray.io/en/latest/rllib/>`_.

Mirrors FinRL's ``finrl/agents/rllib/models.py`` but routes everything
through :class:`BaseRLAgent`. ``ray[rllib]`` is an optional dependency.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym

from aqp.rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


_RLLIB_ALGOS = {
    "PPO": ("ray.rllib.algorithms.ppo", "PPOConfig"),
    "A2C": ("ray.rllib.algorithms.a2c", "A2CConfig"),
    "A3C": ("ray.rllib.algorithms.a3c", "A3CConfig"),
    "DDPG": ("ray.rllib.algorithms.ddpg", "DDPGConfig"),
    "SAC": ("ray.rllib.algorithms.sac", "SACConfig"),
    "TD3": ("ray.rllib.algorithms.td3", "TD3Config"),
    "DQN": ("ray.rllib.algorithms.dqn", "DQNConfig"),
    "IMPALA": ("ray.rllib.algorithms.impala", "ImpalaConfig"),
    "APEX-DQN": ("ray.rllib.algorithms.apex_dqn", "ApexDQNConfig"),
}


def _import_config(name: str):
    if name not in _RLLIB_ALGOS:
        raise KeyError(f"Unknown RLlib algorithm: {name!r}")
    mod_name, cls_name = _RLLIB_ALGOS[name]
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ray[rllib] is not installed. Install with `pip install 'ray[rllib]'`."
        ) from exc
    return getattr(mod, cls_name)


class RayRLlibAdapter(BaseRLAgent):
    """Wraps a Ray RLlib ``Algorithm`` in :class:`BaseRLAgent`."""

    rl_alias: ClassVar[str] = "RayRLlibAdapter"
    rl_source: ClassVar[str] = "rllib"
    rl_category: ClassVar[str] = "drl"
    rl_tags: ClassVar[tuple[str, ...]] = ("ray", "rllib", "scalable")

    def __init__(
        self,
        algorithm: str = "PPO",
        *,
        algo: str | None = None,
        framework: str = "torch",
        num_workers: int = 0,
        num_gpus: float = 0.0,
        config_overrides: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self.algorithm = str(algorithm or algo or "PPO").upper()
        self.framework = str(framework)
        self.num_workers = int(num_workers)
        self.num_gpus = float(num_gpus)
        self.config_overrides = dict(config_overrides or {})
        self.kwargs = dict(kwargs)
        self._algo: Any | None = None

    def _config_for(self, env: gym.Env):
        Config = _import_config(self.algorithm)
        cfg = (
            Config()
            .framework(self.framework)
            .resources(num_gpus=self.num_gpus)
        )
        try:
            cfg = cfg.rollouts(num_rollout_workers=self.num_workers)
        except Exception:  # noqa: BLE001
            pass
        try:
            cfg = cfg.environment(env=lambda env_config: env)
        except Exception:  # noqa: BLE001
            cfg.env = "envs/rllib_aqp_env"  # placeholder
        for k, v in self.config_overrides.items():
            try:
                setter = getattr(cfg, k)
                cfg = setter(**v) if isinstance(v, dict) else setter(v)
            except Exception:  # noqa: BLE001
                logger.debug("RLlib config override failed for %s", k, exc_info=True)
        return cfg

    def build(self, env: gym.Env) -> None:
        cfg = self._config_for(env)
        self._algo = cfg.build()

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self._algo is None:
            raise RuntimeError("RayRLlibAdapter not built. Call .build(env) first.")
        steps_per_iter = max(int(total_timesteps // max(log_interval, 1)), 1)
        for _ in range(int(log_interval)):
            self._algo.train()
            if hasattr(self._algo, "config") and hasattr(self._algo.config, "train_batch_size"):
                if self._algo.config.train_batch_size and steps_per_iter > self._algo.config.train_batch_size:
                    break

    def save(self, path: str | Path) -> Path:
        if self._algo is None:
            raise RuntimeError("RayRLlibAdapter has nothing to save.")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            checkpoint = self._algo.save(str(p.parent))
            return Path(checkpoint)
        except Exception:  # noqa: BLE001
            return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        if env is not None and self._algo is None:
            self.build(env)
        if self._algo is None:
            raise RuntimeError("Build the adapter first.")
        self._algo.restore(str(path))

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        if self._algo is None:
            raise RuntimeError("Build the adapter first.")
        action = self._algo.compute_single_action(obs, explore=not deterministic)
        return action, None

    @property
    def model(self) -> Any:
        return self._algo


__all__ = ["RayRLlibAdapter"]
