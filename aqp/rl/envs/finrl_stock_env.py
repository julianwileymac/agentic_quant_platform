"""FinRL pandas ``StockTradingEnv`` port — share-lot integer trading.

Mirrors ``finrl/meta/env_stock_trading/env_stocktrading.py``:

- ``state_space = 1 + 2*stock_dim + len(indicators)*stock_dim``
- ``action_space = Box(-1, 1, stock_dim)`` → scaled by ``hmax`` and cast to ``int``.
- Sells are processed before buys (low-sorted vs high-sorted).
- Optional turbulence threshold flushes positions to cash.
- Reward = ``Δtotal_asset * reward_scaling`` (terminal step adds gamma-tail).

Loads bars via :func:`aqp.rl.envs.base.load_bars` (Iceberg-backed) so it
plugs straight into AQP's data plane while preserving FinRL's state shape.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from aqp.rl.core.base import RL_KIND_ENV, RLComponent
from aqp.rl.envs.base import load_bars, safe_array, vt_symbols_for


_FINRL_INDICATORS = (
    "macd",
    "boll_ub",
    "boll_lb",
    "rsi_30",
    "cci_30",
    "dx_30",
    "close_30_sma",
    "close_60_sma",
)


class FinRLStockTradingEnv(gym.Env, RLComponent):
    """FinRL pandas StockTradingEnv (share-lot integer trading)."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "FinRLStockTradingEnv"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "share-lot"
    rl_tags: ClassVar[tuple[str, ...]] = ("portfolio", "integer-shares", "hmax")

    def __init__(
        self,
        symbols: list[str],
        start: str,
        end: str,
        *,
        initial_balance: float = 1_000_000.0,
        hmax: int = 100,
        buy_cost_pct: float = 0.001,
        sell_cost_pct: float = 0.001,
        reward_scaling: float = 1e-4,
        indicators: list[str] | None = None,
        turbulence_threshold: float | None = None,
        risk_indicator_col: str = "turbulence",
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.symbols = list(symbols)
        self.stock_dim = len(self.symbols)
        self.initial_balance = float(initial_balance)
        self.hmax = int(hmax)
        self.buy_cost_pct = float(buy_cost_pct)
        self.sell_cost_pct = float(sell_cost_pct)
        self.reward_scaling = float(reward_scaling)
        self.indicators = list(indicators or _FINRL_INDICATORS)
        self.turbulence_threshold = turbulence_threshold
        self.risk_indicator_col = str(risk_indicator_col)

        bars = load_bars(self.symbols, start, end, indicators=self.indicators + [self.risk_indicator_col])
        if bars.empty:
            raise RuntimeError(
                f"FinRLStockTradingEnv: no data for {self.symbols} in {start}..{end}."
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
        if self.risk_indicator_col in bars.columns:
            self.turbulence = bars.groupby("timestamp")[self.risk_indicator_col].mean()
        else:
            self.turbulence = pd.Series(0.0, index=self.price_table.index)

        self.timestamps = self.price_table.index
        self.horizon = len(self.timestamps)

        self.state_space = 1 + 2 * self.stock_dim + len(self.indicators) * self.stock_dim
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(self.stock_dim,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(self.state_space,), dtype=np.float32
        )

        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------ helpers

    def _reset_state(self) -> None:
        self.day = 0
        self.cash = self.initial_balance
        self.shares = np.zeros(self.stock_dim, dtype=np.float64)
        self.cost = 0.0
        self.trades = 0
        self.terminal = False
        self.portfolio_value = self.initial_balance
        self.prev_value = self.initial_balance
        self.peak = self.initial_balance
        self.history: list[float] = [self.initial_balance]

    def _prices(self, idx: int) -> np.ndarray:
        return safe_array(self.price_table.iloc[idx].values)

    def _features(self, idx: int) -> np.ndarray:
        parts = [
            safe_array(table.iloc[idx].values)
            for ind in self.indicators
            for table in [self.feature_tables.get(ind)]
            if table is not None
        ]
        if not parts:
            return np.zeros(self.stock_dim * len(self.indicators), dtype=np.float32)
        return np.concatenate(parts)

    def _turb(self, idx: int) -> float:
        try:
            return float(self.turbulence.iloc[idx])
        except Exception:
            return 0.0

    def _state(self) -> np.ndarray:
        prices = self._prices(self.day)
        return safe_array(
            np.concatenate(
                [
                    [self.cash],
                    prices,
                    self.shares,
                    self._features(self.day),
                ]
            )
        )

    def _sell_stock(self, i: int, action_int: int) -> None:
        if self.shares[i] <= 0 or action_int >= 0:
            return
        sell_qty = min(abs(int(action_int)), int(self.shares[i]))
        if sell_qty <= 0:
            return
        price = float(self.price_table.iloc[self.day].iloc[i])
        proceeds = sell_qty * price * (1.0 - self.sell_cost_pct)
        self.cash += proceeds
        self.shares[i] -= sell_qty
        self.cost += sell_qty * price * self.sell_cost_pct
        self.trades += 1

    def _buy_stock(self, i: int, action_int: int) -> None:
        if action_int <= 0:
            return
        price = float(self.price_table.iloc[self.day].iloc[i])
        if price <= 0:
            return
        max_qty = int(self.cash // (price * (1.0 + self.buy_cost_pct)))
        buy_qty = min(int(action_int), max_qty)
        if buy_qty <= 0:
            return
        cost = buy_qty * price * (1.0 + self.buy_cost_pct)
        self.cash -= cost
        self.shares[i] += buy_qty
        self.cost += buy_qty * price * self.buy_cost_pct
        self.trades += 1

    # ------------------------------------------------------------------ Gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._state(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        action = np.asarray(action, dtype=np.float32).flatten()
        action = (np.clip(action, -1.0, 1.0) * self.hmax).astype(int)
        if (
            self.turbulence_threshold is not None
            and self._turb(self.day) > self.turbulence_threshold
        ):
            action = -np.abs(action)  # forced liquidation

        # Sells first (low-sorted), then buys (high-sorted) — FinRL convention.
        sell_idx = np.argsort(action)
        for i in sell_idx:
            if action[i] < 0:
                self._sell_stock(int(i), int(action[i]))
        buy_idx = np.argsort(action)[::-1]
        for i in buy_idx:
            if action[i] > 0:
                self._buy_stock(int(i), int(action[i]))

        prev_value = self.portfolio_value
        self.day += 1
        self.terminal = self.day >= self.horizon - 1
        prices = self._prices(self.day)
        self.portfolio_value = float(self.cash + np.dot(self.shares, prices))
        self.peak = max(self.peak, self.portfolio_value)
        delta = self.portfolio_value - prev_value
        reward = float(delta * self.reward_scaling)
        self.prev_value = self.portfolio_value
        self.history.append(self.portfolio_value)

        info: dict[str, Any] = {
            "portfolio_value": self.portfolio_value,
            "delta": delta,
            "cost": self.cost,
            "trades": self.trades,
            "drawdown": (self.portfolio_value - self.peak) / self.peak if self.peak else 0.0,
            "timestamp": str(self.timestamps[self.day]),
        }
        return self._state(), reward, bool(self.terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.day,
            "portfolio_value": self.portfolio_value,
            "prev_value": self.prev_value,
            "peak": self.peak,
            "cash": self.cash,
            "shares": self.shares,
            "price_panel": self.price_table,
            "feature_tables": self.feature_tables,
            "turbulence": self.turbulence,
            "initial_balance": self.initial_balance,
            "timestamp": str(self.timestamps[self.day]) if self.day < len(self.timestamps) else None,
        }


from aqp.core.registry import register as _register  # noqa: E402

_register("FinRLStockTradingEnv", kind=RL_KIND_ENV)(FinRLStockTradingEnv)


__all__ = ["FinRLStockTradingEnv"]
