"""Placeholder market-making env.

Future work: pair the Avellaneda-Stoikov model with the AQP order-book
microstructure dataset so the agent learns bid/ask quote placement.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp.rl.core.base import RL_KIND_ENV, RLComponent


class MarketMakingEnv(gym.Env, RLComponent):
    """Stub market-making env (action = ``(half_spread, inventory_skew)``)."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "MarketMakingEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "market-making"
    rl_tags: ClassVar[tuple[str, ...]] = ("placeholder", "market-making")

    def __init__(self, *, horizon: int = 1000, inventory_cap: float = 100.0) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.inventory_cap = float(inventory_cap)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32
        )
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.inventory = 0.0
        self.cash = 0.0
        self.mid = 100.0
        self.portfolio_value = 0.0
        self.history = [0.0]

    def _obs(self) -> np.ndarray:
        return np.asarray(
            [self.mid / 100.0, self.inventory / self.inventory_cap, self.cash / 1000.0, float(self.step_idx) / max(self.horizon, 1)],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        half_spread = float(np.clip(action.flatten()[0], 0.0, 1.0)) * 0.5
        skew = float(np.clip(action.flatten()[1], 0.0, 1.0)) - 0.5
        # Stylised price walk.
        self.mid += float(np.random.normal(scale=0.05))
        bid = self.mid - half_spread + skew * 0.1
        ask = self.mid + half_spread + skew * 0.1
        # Stylised hits: fills proportional to spread inversely.
        if np.random.random() < max(0.0, 0.5 - half_spread):
            self.inventory += 1
            self.cash -= bid
        if np.random.random() < max(0.0, 0.5 - half_spread):
            self.inventory -= 1
            self.cash += ask
        self.portfolio_value = self.cash + self.inventory * self.mid
        self.history.append(self.portfolio_value)
        self.step_idx += 1
        terminal = self.step_idx >= self.horizon or abs(self.inventory) >= self.inventory_cap
        reward = self.portfolio_value - (self.history[-2] if len(self.history) > 1 else 0.0)
        info: dict[str, Any] = {
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "portfolio_value": self.portfolio_value,
        }
        return self._obs(), float(reward), bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "portfolio_value": self.portfolio_value,
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("MarketMakingEnv", kind=RL_KIND_ENV)(MarketMakingEnv)


__all__ = ["MarketMakingEnv"]
