"""Placeholder optimal-execution env (TWAP / VWAP slicing).

Future work: integrate with the AQP microstructure dataset and
order-flow imbalance metrics to make this a research-grade execution env.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent


class ExecutionEnv(gym.Env, RLComponent):
    """Stub optimal-execution env (slice a parent order over ``horizon``)."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "ExecutionEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("placeholder", "execution")

    def __init__(self, *, parent_qty: float = 1000.0, horizon: int = 100) -> None:
        super().__init__()
        self.parent_qty = float(parent_qty)
        self.horizon = int(horizon)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(3,), dtype=np.float32
        )
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.remaining = self.parent_qty
        self.realised_cost = 0.0
        self.history = [0.0]

    def _obs(self) -> np.ndarray:
        progress = 1.0 - (self.remaining / max(self.parent_qty, 1.0))
        time_left = 1.0 - (self.step_idx / max(self.horizon, 1))
        return np.asarray([progress, time_left, self.realised_cost / 1000.0], dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        slice_pct = float(np.clip(action.flatten()[0], 0.0, 1.0))
        slice_qty = min(self.remaining, self.parent_qty * slice_pct)
        self.remaining -= slice_qty
        # Stylised cost: linear with size + small random microstructure noise.
        cost = slice_qty * (0.0001 + 0.0005 * slice_pct)
        self.realised_cost += float(cost)
        self.step_idx += 1
        terminal = self.step_idx >= self.horizon or self.remaining <= 0
        reward = float(-cost)
        if terminal and self.remaining > 0:
            # Penalise unfinished orders.
            reward -= float(self.remaining) * 0.001
        info: dict[str, Any] = {
            "remaining": self.remaining,
            "realised_cost": self.realised_cost,
            "step_idx": self.step_idx,
        }
        self.history.append(self.realised_cost)
        return self._obs(), reward, bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "portfolio_value": -self.realised_cost,
            "remaining": self.remaining,
            "realised_cost": self.realised_cost,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("ExecutionEnv", kind=RL_KIND_ENV)(ExecutionEnv)


__all__ = ["ExecutionEnv"]
