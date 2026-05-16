"""Cartea-Jaimungal optimal liquidation environment.

The agent learns a feedback liquidation rate ``nu`` for a finite-time
block trade. The reference closed-form is the linear-quadratic ansatz
solved by :func:`aqp.optimal_control.cartea_jaimungal.solve` — the
agent's job is to outperform that benchmark in regimes where the
assumed dynamics break (e.g. mean-reverting or jumpy mid).

Observation
===========

- normalised remaining inventory.
- normalised time-to-horizon.
- mid-price drift (last step).
- implied vs realised vol gap.
- cumulative impact paid.

Action
======

Single scalar in ``[-1, 1]`` mapped to ``nu = action * max_rate``.
Positive = sell, negative = buy.

Reward
======

Implementation shortfall: per-step ``execution_price * traded_qty``
minus a quadratic inventory penalty (``phi * q**2``). At horizon the
remaining inventory is force-liquidated at a discount governed by
``alpha``.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp.rl.core.base import RL_KIND_ENV, RLComponent


class OptimalExecutionEnv(gym.Env, RLComponent):
    """Cartea-Jaimungal block-liquidation env."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "OptimalExecutionEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("cartea_jaimungal", "optimal_execution", "hjb")

    def __init__(
        self,
        *,
        horizon: int = 200,
        initial_inventory: float = 100.0,
        sigma: float = 0.01,
        phi: float = 1e-4,
        alpha: float = 1e-3,
        kappa: float = 1.0,
        max_rate: float | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.initial_inventory = float(initial_inventory)
        self.sigma = float(sigma)
        self.phi = float(phi)
        self.alpha = float(alpha)
        self.kappa = float(kappa)
        self.max_rate = float(max_rate) if max_rate else float(initial_inventory) / max(horizon, 1) * 4.0

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(5,), dtype=np.float32
        )
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.inventory = float(self.initial_inventory)
        self.cash = 0.0
        self.mid = 100.0
        self.last_drift = 0.0
        self.cumulative_impact = 0.0

    def _obs(self) -> np.ndarray:
        remaining = self.inventory / max(self.initial_inventory, 1e-6)
        time_left = float(self.horizon - self.step_idx) / max(self.horizon, 1)
        return np.asarray(
            [
                remaining,
                time_left,
                self.last_drift / max(self.sigma, 1e-6),
                0.0,  # vol-gap placeholder (regime-aware extension)
                self.cumulative_impact / 100.0,
            ],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        # Action ∈ [-1, 1]; map to a trading rate ν.
        a = float(np.clip(action.flatten()[0], -1.0, 1.0))
        nu = a * self.max_rate

        # Cap so we don't overshoot remaining inventory.
        if nu > self.inventory:
            nu = self.inventory
        elif nu < -abs(self.inventory):
            nu = -abs(self.inventory)

        # Execution price = mid - kappa * nu (sells push price down).
        impact = self.kappa * nu
        execution_price = self.mid - impact
        self.inventory -= nu
        self.cash += nu * execution_price
        self.cumulative_impact += abs(impact)

        # Mid drifts under GBM.
        drift = self.sigma * float(self._rng.standard_normal())
        self.mid = max(self.mid + drift, 1e-6)
        self.last_drift = drift

        # Step reward = traded value minus inventory penalty.
        running_penalty = self.phi * (self.inventory * self.inventory)
        reward = nu * execution_price - running_penalty

        self.step_idx += 1
        at_terminal = self.step_idx >= self.horizon
        if at_terminal and abs(self.inventory) > 1e-9:
            # Force-liquidate at terminal with the alpha discount.
            terminal_pnl = self.inventory * (self.mid - self.alpha * self.inventory)
            self.cash += terminal_pnl
            reward += terminal_pnl - self.alpha * (self.inventory * self.inventory)
            self.inventory = 0.0

        info: dict[str, Any] = {
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "execution_price": execution_price,
            "rate": nu,
            "cumulative_impact": self.cumulative_impact,
            "portfolio_value": self.cash,
            "peak": max(self.cash, 0.0),
        }
        return self._obs(), float(reward), bool(at_terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "cumulative_impact": self.cumulative_impact,
        }


__all__ = ["OptimalExecutionEnv"]
