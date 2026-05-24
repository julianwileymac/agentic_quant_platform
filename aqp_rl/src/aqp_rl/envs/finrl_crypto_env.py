"""FinRL crypto multi-asset env port — array-backed lookback stack.

Mirrors ``finrl/meta/env_cryptocurrency_trading/env_multiple_crypto.py``:

- ``state = hstack(scaled cash, scaled positions, lookback × tech_row)``
- ``action = continuous per-asset, scaled by per-asset normaliser``
- Per-step reward ``(next_total - total) * 2**-16`` plus terminal
  ``gamma_return``.

Like :class:`FinRLStockTradingNpEnv` this env consumes pre-computed
arrays so any concrete data pipeline can feed it.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent


class FinRLCryptoEnv(gym.Env, RLComponent):
    """Array-backed FinRL crypto env with lookback feature stacking."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "FinRLCryptoEnv"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "crypto-lookback"
    rl_tags: ClassVar[tuple[str, ...]] = ("crypto", "numpy", "lookback")

    def __init__(
        self,
        *,
        price_array: np.ndarray,
        tech_array: np.ndarray,
        lookback: int = 5,
        initial_capital: float = 100_000.0,
        buy_cost_pct: float = 0.001,
        sell_cost_pct: float = 0.001,
        gamma: float = 0.99,
    ) -> None:
        super().__init__()
        self.price_array = np.asarray(price_array, dtype=np.float32)
        self.tech_array = np.asarray(tech_array, dtype=np.float32)
        self.lookback = int(lookback)
        self.initial_capital = float(initial_capital)
        self.buy_cost_pct = float(buy_cost_pct)
        self.sell_cost_pct = float(sell_cost_pct)
        self.gamma = float(gamma)

        self.n_crypto = self.price_array.shape[1] if self.price_array.ndim > 1 else 1
        self.tech_dim = self.tech_array.shape[1] if self.tech_array.ndim > 1 else 0
        self.max_step = int(self.price_array.shape[0]) - 1

        self.state_dim = 1 + self.n_crypto + (self.tech_dim) * self.lookback
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(self.n_crypto,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.state_dim,), dtype=np.float32
        )

        self.action_normaliser = self._compute_normaliser()
        self._reset_state()

    def _compute_normaliser(self) -> np.ndarray:
        if self.price_array.size == 0:
            return np.ones(self.n_crypto, dtype=np.float32)
        ref = self.price_array[0] if self.price_array.ndim > 1 else self.price_array[:1]
        ref = np.where(ref == 0, 1.0, ref)
        return (1.0 / ref).astype(np.float32)

    def _reset_state(self) -> None:
        self.time = self.lookback
        self.cash = self.initial_capital
        self.stocks = np.zeros(self.n_crypto, dtype=np.float32)
        self.total_asset = self.initial_capital
        self.episode_return = 0.0
        self.gamma_return = 0.0
        self.history: list[float] = [self.initial_capital]

    def _state(self) -> np.ndarray:
        state = np.hstack(
            [
                [self.cash * 2 ** -18],
                self.stocks * 2 ** -3,
            ]
        )
        for i in range(self.lookback):
            t = max(0, self.time - i)
            tech_i = self.tech_array[t] if self.tech_array.size else np.zeros(0, dtype=np.float32)
            state = np.hstack([state, tech_i * 2 ** -15])
        return state.astype(np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._state(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        action = np.asarray(action, dtype=np.float32).flatten()
        action = action * self.action_normaliser
        prices = self.price_array[self.time]
        # Sells.
        for i in range(self.n_crypto):
            if action[i] < 0 and self.stocks[i] > 0:
                qty = min(float(-action[i]), float(self.stocks[i]))
                self.cash += float(prices[i]) * qty * (1.0 - self.sell_cost_pct)
                self.stocks[i] -= qty
        # Buys.
        for i in range(self.n_crypto):
            if action[i] > 0 and prices[i] > 0:
                qty = float(action[i])
                cost = float(prices[i]) * qty * (1.0 + self.buy_cost_pct)
                if cost <= self.cash:
                    self.cash -= cost
                    self.stocks[i] += qty
        self.time += 1
        prices = self.price_array[self.time]
        new_total = float(self.cash + np.dot(self.stocks, prices))
        reward = (new_total - self.total_asset) * 2 ** -16
        self.total_asset = new_total
        self.gamma_return = self.gamma_return * self.gamma + reward
        self.history.append(self.total_asset)
        done = self.time >= self.max_step
        if done:
            reward = self.gamma_return
            self.episode_return = self.total_asset / self.initial_capital
        info: dict[str, Any] = {
            "portfolio_value": self.total_asset,
            "step_idx": self.time,
            "episode_return": self.episode_return,
        }
        return self._state(), float(reward), bool(done), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.time,
            "portfolio_value": self.total_asset,
            "prev_value": self.history[-2] if len(self.history) > 1 else self.total_asset,
            "cash": self.cash,
            "stocks": self.stocks,
            "initial_balance": self.initial_capital,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("FinRLCryptoEnv", kind=RL_KIND_ENV)(FinRLCryptoEnv)


__all__ = ["FinRLCryptoEnv"]
