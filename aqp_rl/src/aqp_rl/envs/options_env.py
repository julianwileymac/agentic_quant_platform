"""Placeholder env for options-trading research.

Future work: integrate with :class:`aqp.persistence.models.OptionSeries`
and :class:`OptionChainSnapshot` to build a Greek-aware action space
(target delta / vega / gamma exposures). For now this is a minimal
scaffold so the registry surfaces it in the lab palette.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent


class OptionsTradingEnv(gym.Env, RLComponent):
    """Stub options trading env (delta / vega / gamma target action)."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "OptionsTradingEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "options"
    rl_tags: ClassVar[tuple[str, ...]] = ("placeholder", "options")

    def __init__(self, *, n_targets: int = 3, horizon: int = 252) -> None:
        super().__init__()
        self.n_targets = int(n_targets)
        self.horizon = int(horizon)
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(self.n_targets,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.n_targets * 2,), dtype=np.float32
        )
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.targets = np.zeros(self.n_targets, dtype=np.float32)
        self.realised = np.zeros(self.n_targets, dtype=np.float32)
        self.portfolio_value = 100_000.0
        self.prev_value = 100_000.0
        self.history = [self.portfolio_value]

    def _obs(self) -> np.ndarray:
        return np.concatenate([self.targets, self.realised]).astype(np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        action = np.asarray(action, dtype=np.float32).flatten()
        self.targets = action
        # Placeholder: realised exposures = noisy version of targets.
        self.realised = action + np.random.normal(scale=0.05, size=self.n_targets).astype(np.float32)
        self.step_idx += 1
        terminal = self.step_idx >= self.horizon
        reward = float(-np.sum(np.abs(self.realised - self.targets)))
        info: dict[str, Any] = {
            "portfolio_value": self.portfolio_value,
            "targets": self.targets.tolist(),
            "realised": self.realised.tolist(),
        }
        self.history.append(self.portfolio_value)
        return self._obs(), reward, bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "portfolio_value": self.portfolio_value,
            "prev_value": self.prev_value,
            "targets": self.targets,
            "realised": self.realised,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("OptionsTradingEnv", kind=RL_KIND_ENV)(OptionsTradingEnv)


__all__ = ["OptionsTradingEnv"]
