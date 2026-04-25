"""Portfolio allocation env — action = simplex weights over N assets.

Differs from :class:`StockTradingEnv` in that it softmax-normalises the
action to a probability-like weight vector (no cash). Useful for PPO/DDPG
portfolio allocation research.
"""
from __future__ import annotations

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp.core.registry import register
from aqp.rl.envs.base import default_reward, load_bars, pivot_features, safe_array


@register("PortfolioAllocationEnv")
class PortfolioAllocationEnv(gym.Env):
    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        symbols: list[str],
        start: str,
        end: str,
        initial_balance: float = 100000.0,
        transaction_cost_pct: float = 0.001,
        indicators: list[str] | None = None,
        reward_scaling: float = 1e-4,
    ) -> None:
        super().__init__()
        self.symbols = list(symbols)
        self.n = len(self.symbols)
        self.indicators = indicators or ["macd", "rsi_14", "sma_20"]
        self.initial_balance = float(initial_balance)
        self.cost_pct = float(transaction_cost_pct)
        self.reward_scaling = float(reward_scaling)

        bars = load_bars(self.symbols, start, end, indicators=self.indicators)
        if bars.empty:
            raise RuntimeError(
                f"PortfolioAllocationEnv: no data for {self.symbols} in {start}..{end}."
            )
        self.price_table = bars.pivot(index="timestamp", columns="vt_symbol", values="close")
        self.price_table = self.price_table.reindex(columns=self._vt_for_symbols()).ffill().bfill()
        feats = pivot_features(bars, self.indicators)
        self.feature_tables = {
            k: v.reindex(columns=self._vt_for_symbols()).ffill().bfill() for k, v in feats.items()
        }
        self.timestamps = self.price_table.index
        self.horizon = len(self.timestamps)

        obs_dim = self.n + self.n * len(self.indicators)
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.n,), dtype=np.float32)

        self._reset_state()

    def _vt_for_symbols(self) -> list[str]:
        return [s if "." in s else f"{s}.NASDAQ" for s in self.symbols]

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.portfolio_value = self.initial_balance
        self.prev_value = self.initial_balance
        self.weights = np.ones(self.n, dtype=np.float32) / max(self.n, 1)
        self.history = [self.portfolio_value]

    def _prices(self, idx: int) -> np.ndarray:
        return safe_array(self.price_table.iloc[idx].values)

    def _features(self, idx: int) -> np.ndarray:
        parts = []
        for name in self.indicators:
            table = self.feature_tables.get(name)
            if table is None:
                parts.append(np.zeros(self.n, dtype=np.float32))
            else:
                parts.append(safe_array(table.iloc[idx].values))
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)

    def _obs(self) -> np.ndarray:
        return safe_array(np.concatenate([self.weights, self._features(self.step_idx)]))

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):
        action = np.clip(np.asarray(action, dtype=np.float32), 0.0, 1.0)
        total = action.sum()
        weights = action / total if total > 1e-9 else np.ones_like(action) / len(action)

        self.step_idx += 1
        done = self.step_idx >= self.horizon - 1

        prev = self._prices(self.step_idx - 1)
        curr = self._prices(self.step_idx)
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = np.where(prev > 0, curr / prev - 1.0, 0.0)

        gross = float(1.0 + np.dot(self.weights, ret))
        turnover = float(np.sum(np.abs(weights - self.weights)))
        self.portfolio_value *= gross
        self.portfolio_value *= max(0.0, 1.0 - turnover * self.cost_pct)
        self.weights = weights

        reward = default_reward(
            self.portfolio_value, self.prev_value, turnover, self.cost_pct, scale=self.reward_scaling
        )
        self.prev_value = self.portfolio_value
        self.history.append(self.portfolio_value)

        info = {
            "portfolio_value": self.portfolio_value,
            "weights": weights.tolist(),
            "timestamp": str(self.timestamps[self.step_idx]),
        }
        return self._obs(), reward, bool(done), False, info
