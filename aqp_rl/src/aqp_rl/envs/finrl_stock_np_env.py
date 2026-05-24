"""FinRL numpy ``StockTradingEnv`` port — array-backed fast path.

Mirrors ``finrl/meta/env_stock_trading/env_stocktrading_np.py``:

- ``state_dim = 1 + 2 + 3*stock_dim + tech_dim``
- Per-step reward = ``Δtotal_asset * reward_scaling``; terminal step
  emits the gamma-discounted cumulative reward.
- Turbulence boolean array; positions liquidated when triggered.

Designed for ElegantRL / RLlib's array vec-envs. Builds its arrays from
:meth:`aqp_rl.core.data.BaseDataPipeline.run_full` so any concrete
pipeline (Iceberg, Yahoo, Alpaca) can feed this env without code changes.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent


class FinRLStockTradingNpEnv(gym.Env, RLComponent):
    """Array-backed FinRL stock trading env."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "FinRLStockTradingNpEnv"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "array-backed"
    rl_tags: ClassVar[tuple[str, ...]] = ("portfolio", "numpy", "fast")

    def __init__(
        self,
        *,
        price_array: np.ndarray,
        tech_array: np.ndarray,
        turbulence_array: np.ndarray,
        if_train: bool = True,
        initial_capital: float = 1_000_000.0,
        max_stock: int = 100,
        buy_cost_pct: float = 0.001,
        sell_cost_pct: float = 0.001,
        reward_scaling: float = 2 ** -11,
        gamma: float = 0.99,
        turbulence_thresh: float = 99.0,
    ) -> None:
        super().__init__()
        self.price_array = np.asarray(price_array, dtype=np.float32)
        self.tech_array = np.asarray(tech_array, dtype=np.float32)
        self.turbulence_array = np.asarray(turbulence_array, dtype=np.float32)
        self.if_train = bool(if_train)
        self.initial_capital = float(initial_capital)
        self.max_stock = int(max_stock)
        self.buy_cost_pct = float(buy_cost_pct)
        self.sell_cost_pct = float(sell_cost_pct)
        self.reward_scaling = float(reward_scaling)
        self.gamma = float(gamma)
        self.turbulence_thresh = float(turbulence_thresh)

        self.stock_dim = self.price_array.shape[1] if self.price_array.ndim > 1 else 1
        self.tech_dim = self.tech_array.shape[1] if self.tech_array.ndim > 1 else 0
        self.state_dim = 1 + 2 + 3 * self.stock_dim + self.tech_dim
        self.max_step = int(self.price_array.shape[0]) - 1

        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(self.stock_dim,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-3000.0, high=3000.0, shape=(self.state_dim,), dtype=np.float32
        )

        self._reset_state()

    def _reset_state(self) -> None:
        self.day = 0
        self.cash = self.initial_capital
        self.stocks = np.zeros(self.stock_dim, dtype=np.float32)
        self.stocks_cool_down = np.zeros(self.stock_dim, dtype=np.float32)
        self.total_asset = self.initial_capital
        self.episode_return = 0.0
        self.gamma_reward = 0.0
        self.history: list[float] = [self.initial_capital]

    def _state(self) -> np.ndarray:
        prices = self.price_array[self.day]
        tech_row = self.tech_array[self.day] if self.tech_array.size else np.zeros(0, dtype=np.float32)
        turb = self.turbulence_array[self.day] if self.turbulence_array.size else 0.0
        state = np.hstack(
            [
                [self.cash * 2 ** -18, float(turb), float(turb > self.turbulence_thresh)],
                self.stocks * 2 ** -3,
                self.stocks_cool_down,
                prices * 2 ** -7,
                tech_row * 2 ** -15,
            ]
        ).astype(np.float32)
        return np.nan_to_num(state, nan=0.0, posinf=0.0, neginf=0.0)

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._state(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        action = np.asarray(action, dtype=np.float32).flatten()
        actions_int = (np.clip(action, -1.0, 1.0) * self.max_stock).astype(int)
        prices = self.price_array[self.day]
        if (
            self.turbulence_array.size
            and float(self.turbulence_array[self.day]) > self.turbulence_thresh
        ):
            actions_int = -np.abs(actions_int)

        # Sells first.
        sell_idx = np.argsort(actions_int)
        for i in sell_idx:
            qty = -actions_int[i]
            if qty > 0 and self.stocks[i] > 0:
                qty = min(int(qty), int(self.stocks[i]))
                self.cash += float(prices[i]) * qty * (1.0 - self.sell_cost_pct)
                self.stocks[i] -= qty
                self.stocks_cool_down[i] = 0
        # Buys.
        buy_idx = np.argsort(actions_int)[::-1]
        for i in buy_idx:
            qty = actions_int[i]
            if qty > 0 and prices[i] > 0:
                affordable = int(self.cash // (float(prices[i]) * (1.0 + self.buy_cost_pct)))
                qty = min(int(qty), affordable)
                if qty <= 0:
                    continue
                self.cash -= float(prices[i]) * qty * (1.0 + self.buy_cost_pct)
                self.stocks[i] += qty
                self.stocks_cool_down[i] = 1

        self.day += 1
        prices = self.price_array[self.day]
        new_total = float(self.cash + np.dot(self.stocks, prices))
        reward = (new_total - self.total_asset) * self.reward_scaling
        self.total_asset = new_total
        self.gamma_reward = self.gamma_reward * self.gamma + reward
        self.history.append(self.total_asset)
        done = self.day >= self.max_step
        if done:
            reward = self.gamma_reward
            self.episode_return = self.total_asset / self.initial_capital
        info: dict[str, Any] = {
            "portfolio_value": self.total_asset,
            "step_idx": self.day,
            "episode_return": self.episode_return,
        }
        return self._state(), float(reward), bool(done), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.day,
            "portfolio_value": self.total_asset,
            "prev_value": self.history[-2] if len(self.history) > 1 else self.total_asset,
            "cash": self.cash,
            "stocks": self.stocks,
            "initial_balance": self.initial_capital,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("FinRLStockTradingNpEnv", kind=RL_KIND_ENV)(FinRLStockTradingNpEnv)


__all__ = ["FinRLStockTradingNpEnv"]
