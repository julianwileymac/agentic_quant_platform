"""FinRL-style single-portfolio trading env with continuous weights.

State = [cash_ratio, per-symbol weights, per-symbol technical indicators]
Action = desired weight vector, in [-1, 1]^N
Reward = Δportfolio_value scaled, minus turnover cost, minus drawdown penalty
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from aqp.core.registry import register
from aqp.rl.envs.base import default_reward, load_bars, pivot_features, safe_array

_DEFAULT_INDICATORS = ("macd", "rsi_14", "sma_20", "sma_50")


@register("StockTradingEnv")
class StockTradingEnv(gym.Env):
    """Continuous-action portfolio env over a fixed basket of symbols."""

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
        turbulence_threshold: float | None = None,
        max_weight: float = 1.0,
        allow_short: bool = False,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.symbols = list(symbols)
        self.n = len(self.symbols)
        self.indicators = list(indicators or _DEFAULT_INDICATORS)
        self.initial_balance = float(initial_balance)
        self.cost_pct = float(transaction_cost_pct)
        self.reward_scaling = float(reward_scaling)
        self.turbulence_threshold = turbulence_threshold
        self.max_weight = float(max_weight)
        self.allow_short = bool(allow_short)

        bars = load_bars(self.symbols, start, end, indicators=self.indicators + ["turbulence"])
        if bars.empty:
            raise RuntimeError(
                f"StockTradingEnv: no data for {self.symbols} in {start}..{end}. Did you run `make ingest`?"
            )
        self.price_table = bars.pivot(index="timestamp", columns="vt_symbol", values="close").ffill()
        self.price_table = self.price_table.reindex(columns=self._vt_for_symbols()).ffill().bfill()
        feats = pivot_features(bars, self.indicators)
        self.feature_tables = {
            k: v.reindex(columns=self._vt_for_symbols()).ffill().bfill() for k, v in feats.items()
        }
        if "turbulence" in bars.columns:
            self.turbulence = bars.groupby("timestamp")["turbulence"].mean()
        else:
            self.turbulence = pd.Series(0.0, index=self.price_table.index)

        self.timestamps = self.price_table.index
        self.horizon = len(self.timestamps)
        if self.horizon < 2:
            raise RuntimeError("Not enough bars to train.")

        obs_dim = 1 + self.n + self.n * len(self.indicators) + 1  # cash, weights, features, turbulence
        low = np.full(obs_dim, -np.inf, dtype=np.float32)
        high = np.full(obs_dim, np.inf, dtype=np.float32)
        self.observation_space = spaces.Box(low=low, high=high, dtype=np.float32)
        low_act = -1.0 if self.allow_short else 0.0
        self.action_space = spaces.Box(
            low=low_act, high=1.0, shape=(self.n,), dtype=np.float32
        )

        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # --- helpers ------------------------------------------------------
    def _vt_for_symbols(self) -> list[str]:
        return [s if "." in s else f"{s}.NASDAQ" for s in self.symbols]

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.cash = self.initial_balance
        self.weights = np.zeros(self.n, dtype=np.float32)
        self.portfolio_value = self.initial_balance
        self.prev_value = self.initial_balance
        self.peak = self.initial_balance
        self.history: list[float] = [self.initial_balance]
        self.actions_log: list[np.ndarray] = []

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

    def _turb(self, idx: int) -> float:
        try:
            return float(self.turbulence.iloc[idx])
        except Exception:
            return 0.0

    def _obs(self) -> np.ndarray:
        self._prices(self.step_idx)
        invested = self.weights * self.portfolio_value
        cash_ratio = (self.portfolio_value - invested.sum()) / max(self.portfolio_value, 1e-9)
        obs = np.concatenate(
            [
                [cash_ratio],
                self.weights,
                self._features(self.step_idx),
                [self._turb(self.step_idx) / 100.0],
            ]
        )
        return safe_array(obs)

    # --- gym API ------------------------------------------------------
    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):
        action = np.asarray(action, dtype=np.float32)
        if not self.allow_short:
            action = np.clip(action, 0.0, self.max_weight)
        else:
            action = np.clip(action, -self.max_weight, self.max_weight)
        total = np.sum(np.abs(action))
        if total > 1.0:
            action = action / total
        if self.turbulence_threshold is not None and self._turb(self.step_idx) > self.turbulence_threshold:
            action = np.zeros_like(action)

        old_weights = self.weights
        new_weights = action
        turnover = float(np.sum(np.abs(new_weights - old_weights)))

        self.step_idx += 1
        done = self.step_idx >= self.horizon - 1

        prev_prices = self._prices(self.step_idx - 1)
        curr_prices = self._prices(self.step_idx)
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = np.where(prev_prices > 0, curr_prices / prev_prices - 1.0, 0.0)

        gross = float(1.0 + np.dot(old_weights, ret))
        self.portfolio_value *= gross
        self.portfolio_value *= max(0.0, 1.0 - turnover * self.cost_pct)
        self.weights = new_weights
        self.peak = max(self.peak, self.portfolio_value)
        dd = (self.portfolio_value - self.peak) / self.peak

        reward = default_reward(
            current_value=self.portfolio_value,
            previous_value=self.prev_value,
            turnover=turnover,
            cost_pct=self.cost_pct,
            drawdown=dd,
            drawdown_penalty=0.05,
            scale=self.reward_scaling,
        )
        self.prev_value = self.portfolio_value
        self.history.append(self.portfolio_value)
        self.actions_log.append(action)

        info: dict[str, Any] = {
            "portfolio_value": self.portfolio_value,
            "turnover": turnover,
            "drawdown": dd,
            "timestamp": str(self.timestamps[self.step_idx]),
        }
        return self._obs(), reward, bool(done), False, info

    def render(self):  # pragma: no cover
        print(
            f"t={self.step_idx} | pv={self.portfolio_value:.2f} | "
            f"weights={np.round(self.weights, 3).tolist()}"
        )
