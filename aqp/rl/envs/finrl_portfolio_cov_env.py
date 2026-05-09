"""FinRL ``StockPortfolioEnv`` port — covariance + softmax weights.

Mirrors ``finrl/meta/env_portfolio_allocation/env_portfolio.py``:

- Observation: ``[cov_matrix; tech_indicators]`` (2-D shape).
- Action: ``Box(0, 1, stock_dim)`` → softmax weights.
- Reward: portfolio value level (matches FinRL's
  ``self.reward = new_portfolio_value`` convention).
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from aqp.rl.core.base import RL_KIND_ENV, RLComponent
from aqp.rl.envs.base import load_bars, vt_symbols_for


_DEFAULT_INDICATORS = ("macd", "rsi_30", "cci_30", "dx_30")


class FinRLPortfolioCovEnv(gym.Env, RLComponent):
    """FinRL covariance-portfolio env."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "FinRLPortfolioCovEnv"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "covariance-softmax"
    rl_tags: ClassVar[tuple[str, ...]] = ("portfolio", "covariance", "softmax")

    def __init__(
        self,
        symbols: list[str],
        start: str,
        end: str,
        *,
        initial_balance: float = 1_000_000.0,
        transaction_cost_pct: float = 0.001,
        indicators: list[str] | None = None,
        lookback: int = 60,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.symbols = list(symbols)
        self.stock_dim = len(self.symbols)
        self.initial_balance = float(initial_balance)
        self.cost_pct = float(transaction_cost_pct)
        self.indicators = list(indicators or _DEFAULT_INDICATORS)
        self.lookback = int(lookback)

        bars = load_bars(self.symbols, start, end, indicators=self.indicators)
        if bars.empty:
            raise RuntimeError(
                f"FinRLPortfolioCovEnv: no data for {self.symbols} in {start}..{end}."
            )
        vts = vt_symbols_for(self.symbols)
        self.price_table = (
            bars.pivot(index="timestamp", columns="vt_symbol", values="close")
            .reindex(columns=vts)
            .ffill()
            .bfill()
        )
        self.feature_tables: dict[str, pd.DataFrame] = {}
        for ind in self.indicators:
            if ind in bars.columns:
                self.feature_tables[ind] = (
                    bars.pivot(index="timestamp", columns="vt_symbol", values=ind)
                    .reindex(columns=vts)
                    .ffill()
                    .bfill()
                )
        self.timestamps = self.price_table.index
        self.horizon = len(self.timestamps)

        # Observation = covariance row stacked with indicator rows.
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.stock_dim + len(self.indicators), self.stock_dim),
            dtype=np.float32,
        )
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(self.stock_dim,), dtype=np.float32)

        self._rng = np.random.default_rng(seed)
        self._reset_state()

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32) - float(np.max(x))
        e = np.exp(x)
        s = float(np.sum(e))
        return e / s if s > 1e-9 else np.ones_like(e) / max(len(e), 1)

    def _reset_state(self) -> None:
        self.day = self.lookback
        self.weights = np.ones(self.stock_dim, dtype=np.float32) / max(self.stock_dim, 1)
        self.portfolio_value = self.initial_balance
        self.prev_value = self.initial_balance
        self.history: list[float] = [self.initial_balance]

    def _cov(self, idx: int) -> np.ndarray:
        window_start = max(0, int(idx) - self.lookback)
        window = self.price_table.iloc[window_start : int(idx) + 1]
        if len(window) < 2:
            return np.zeros((self.stock_dim, self.stock_dim), dtype=np.float32)
        try:
            return window.pct_change().dropna().cov().values.astype(np.float32)
        except Exception:  # noqa: BLE001
            return np.zeros((self.stock_dim, self.stock_dim), dtype=np.float32)

    def _features(self, idx: int) -> np.ndarray:
        rows = []
        for ind in self.indicators:
            table = self.feature_tables.get(ind)
            if table is None:
                rows.append(np.zeros(self.stock_dim, dtype=np.float32))
            else:
                try:
                    rows.append(table.iloc[idx].values.astype(np.float32))
                except Exception:  # noqa: BLE001
                    rows.append(np.zeros(self.stock_dim, dtype=np.float32))
        if not rows:
            return np.zeros((0, self.stock_dim), dtype=np.float32)
        return np.vstack(rows)

    def _state(self) -> np.ndarray:
        cov = self._cov(self.day)
        feats = self._features(self.day)
        return np.nan_to_num(np.vstack([cov, feats]).astype(np.float32))

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._state(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        weights = self._softmax(action)
        prev_prices = self.price_table.iloc[self.day - 1].values.astype(np.float32)
        self.day += 1
        terminal = self.day >= self.horizon - 1
        curr_prices = self.price_table.iloc[self.day].values.astype(np.float32)
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = np.where(prev_prices > 0, curr_prices / prev_prices - 1.0, 0.0)
        portfolio_return = float(np.dot(weights, ret))
        turnover = float(np.sum(np.abs(weights - self.weights)))
        new_value = self.portfolio_value * (1.0 + portfolio_return)
        new_value *= max(0.0, 1.0 - turnover * self.cost_pct)
        self.weights = weights.astype(np.float32)
        self.prev_value = self.portfolio_value
        self.portfolio_value = float(new_value)
        self.history.append(self.portfolio_value)
        reward = float(self.portfolio_value)  # FinRL convention.
        info: dict[str, Any] = {
            "portfolio_value": self.portfolio_value,
            "weights": weights.tolist(),
            "turnover": turnover,
            "timestamp": str(self.timestamps[self.day]),
        }
        return self._state(), reward, bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.day,
            "portfolio_value": self.portfolio_value,
            "prev_value": self.prev_value,
            "weights": self.weights,
            "price_panel": self.price_table,
            "feature_tables": self.feature_tables,
            "initial_balance": self.initial_balance,
            "timestamp": str(self.timestamps[self.day]) if self.day < len(self.timestamps) else None,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("FinRLPortfolioCovEnv", kind=RL_KIND_ENV)(FinRLPortfolioCovEnv)


__all__ = ["FinRLPortfolioCovEnv"]
