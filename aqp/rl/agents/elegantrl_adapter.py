"""Thin adapter over `ElegantRL <https://github.com/AI4Finance-Foundation/ElegantRL>`_.

Mirrors FinRL's ``finrl/agents/elegantrl/models.py`` but plugged into
the AQP :class:`BaseRLAgent` contract. Lazy-imports ElegantRL so
installing it remains optional (declare the ``rl-elegantrl`` extra
in :file:`pyproject.toml`).

Supported algorithms (FinRL parity):
``PPO``, ``A2C``, ``DDPG``, ``SAC``, ``TD3``, ``DQN``.
"""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym

from aqp.rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


_ELEGANTRL_AGENTS = {
    "PPO": "AgentPPO",
    "A2C": "AgentA2C",
    "DDPG": "AgentDDPG",
    "SAC": "AgentSAC",
    "TD3": "AgentTD3",
    "DQN": "AgentDQN",
}


def _import_elegantrl():
    try:
        return importlib.import_module("elegantrl")
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "ElegantRL is not installed. Install with `pip install elegantrl`."
        ) from exc


class ElegantRLAdapter(BaseRLAgent):
    """Adapter over ElegantRL's agent + ``train_and_evaluate`` loop."""

    rl_alias: ClassVar[str] = "ElegantRLAdapter"
    rl_source: ClassVar[str] = "elegantrl"
    rl_category: ClassVar[str] = "drl"
    rl_tags: ClassVar[tuple[str, ...]] = ("elegantrl", "ppo", "ddpg", "sac", "td3")

    def __init__(
        self,
        algorithm: str = "PPO",
        *,
        algo: str | None = None,
        net_dim: int = 128,
        gamma: float = 0.99,
        learning_rate: float = 1e-4,
        random_seed: int = 0,
        **agent_kwargs: Any,
    ) -> None:
        self.algorithm = str(algorithm or algo or "PPO").upper()
        if self.algorithm not in _ELEGANTRL_AGENTS:
            raise KeyError(f"Unknown ElegantRL algorithm: {self.algorithm!r}")
        self.net_dim = int(net_dim)
        self.gamma = float(gamma)
        self.learning_rate = float(learning_rate)
        self.random_seed = int(random_seed)
        self.agent_kwargs = dict(agent_kwargs)
        self._agent: Any | None = None
        self._env: gym.Env | None = None
        self._cwd: Path | None = None

    def build(self, env: gym.Env) -> None:
        elegantrl = _import_elegantrl()
        agent_cls = getattr(elegantrl, _ELEGANTRL_AGENTS[self.algorithm], None)
        if agent_cls is None:
            agent_cls = getattr(elegantrl.agents, _ELEGANTRL_AGENTS[self.algorithm])
        self._env = env
        try:
            state_dim = int(env.observation_space.shape[0])
        except Exception:  # noqa: BLE001
            state_dim = 1
        try:
            action_dim = int(env.action_space.shape[0]) if hasattr(env.action_space, "shape") and env.action_space.shape else int(env.action_space.n)
        except Exception:  # noqa: BLE001
            action_dim = 1
        try:
            self._agent = agent_cls(net_dim=self.net_dim, state_dim=state_dim, action_dim=action_dim, **self.agent_kwargs)
        except TypeError:
            # Fallback for newer ElegantRL signatures.
            self._agent = agent_cls()
            init = getattr(self._agent, "init", None)
            if callable(init):
                init(self.net_dim, state_dim, action_dim, learning_rate=self.learning_rate, gamma=self.gamma)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        if self._agent is None or self._env is None:
            raise RuntimeError("ElegantRLAdapter not built. Call .build(env) first.")
        elegantrl = _import_elegantrl()
        train_fn = getattr(elegantrl.train, "train_and_evaluate", None) or getattr(
            elegantrl, "train_and_evaluate", None
        )
        if train_fn is None:
            raise RuntimeError(
                "ElegantRL is missing train_and_evaluate; cannot run training."
            )
        Config = getattr(elegantrl.train, "Config", None) or getattr(elegantrl, "Config")
        cfg = Config(self._agent.__class__, env=self._env)
        cfg.gamma = self.gamma
        cfg.learning_rate = self.learning_rate
        cfg.target_step = int(total_timesteps)
        cfg.random_seed = self.random_seed
        train_fn(cfg)

    def save(self, path: str | Path) -> Path:
        if self._agent is None:
            raise RuntimeError("ElegantRLAdapter has nothing to save.")
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._agent.save_or_load_agent(str(p.parent), if_save=True)
        except Exception:
            try:
                import torch

                torch.save(self._agent.act.state_dict(), str(p))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"ElegantRLAdapter save failed: {exc}") from exc
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        if env is not None and self._env is None:
            self.build(env)
        if self._agent is None:
            raise RuntimeError("Build the adapter first (call .build(env)).")
        try:
            self._agent.save_or_load_agent(str(Path(path).parent), if_save=False)
        except Exception:
            import torch

            self._agent.act.load_state_dict(torch.load(str(path)))

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        if self._agent is None:
            raise RuntimeError("Build the adapter first.")
        try:
            import numpy as np
            import torch

            obs_t = torch.as_tensor(np.asarray(obs, dtype="float32"))
            if obs_t.ndim == 1:
                obs_t = obs_t.unsqueeze(0)
            action = self._agent.act(obs_t).detach().cpu().numpy()[0]
            return action, None
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"ElegantRLAdapter predict failed: {exc}") from exc

    @property
    def model(self) -> Any:
        return self._agent


__all__ = ["ElegantRLAdapter"]
