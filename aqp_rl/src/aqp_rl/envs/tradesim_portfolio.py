"""``PortfolioManagementEnv`` — EIIE-style multi-asset portfolio env.

Port of TradeMaster's
``trademaster/environments/portfolio_management/{environment,eiie_environment}.py``
into AQP's :class:`BaseRLEnv` / metaclass conventions, with two
production improvements:

1. ``BaseDataset``-friendly data input (no direct ``pd.read_csv``).
2. Gymnasium 5-tuple step contract (``terminated``, ``truncated``).

Action space
============

``Box(0, 1, shape=(N+1,))`` — cash + N tickers. The env softmax-
fallback-normalises the raw action so a policy can emit either
unnormalised logits or a pre-normalised simplex vector and the
weights always sum to 1.

Observation
===========

``(F, N, T)`` tensor — F technical indicators × N stocks × T-bar
window. Matches the EIIE convolutional policy's input shape; reduces
to ``(F, N)`` when ``time_steps=1`` for the simpler portfolio envs.

Reward
======

The env's default reward is the per-step log-return after applying
turnover-driven transaction costs::

    pv_new = (pv_old − fee) · (1 + Σ weights · price_ratios)
    fee = transaction_cost_pct · pv_old · Σ |w_drifted_prev − w_now|
    reward = log(pv_new / pv_old)

The fee model mirrors TradeMaster's "soft commission via weight-drift
recalc" pattern, where the post-execution weights ``w_drifted`` are
distinct from the policy's commanded weights because per-asset price
moves drift the realised weight vector between rebalances.
"""
from __future__ import annotations

import logging
import math
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent
from aqp_rl.envs.tradesim_base import (
    coerce_to_dataframe,
    normalise_weights,
    safe_pct_change,
    softmax_with_cash,
    stamp_step_info,
    validate_columns,
)

logger = logging.getLogger(__name__)


_REQUIRED_COLS = ("date", "tic", "close")


class PortfolioManagementEnv(gym.Env, RLComponent):
    """EIIE-style portfolio management env with softmax weight action.

    Parameters
    ----------
    data:
        DataFrame (or :class:`BaseDataset`) with one row per
        ``(date, tic)`` pair. Must include ``date``, ``tic``, ``close``,
        and every column listed in ``tech_indicator_list``.
    initial_amount:
        Starting cash. Default ``100_000``.
    transaction_cost_pct:
        Per-rebalance fraction applied to turnover. Default ``0.001``.
    tech_indicator_list:
        Per-ticker per-step feature columns.
    time_steps:
        EIIE-style time window stacked into each observation. Default
        ``10`` matching TradeMaster's EIIE env; ``1`` recovers the
        flat ``(F, N)`` observation shape of the simpler PM env.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "tradesim_portfolio"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "portfolio_management"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "eiie",
        "portfolio",
        "softmax",
        "multi_asset",
    )

    def __init__(
        self,
        *,
        data: Any,
        initial_amount: float = 100_000.0,
        transaction_cost_pct: float = 0.001,
        tech_indicator_list: list[str] | None = None,
        time_steps: int = 10,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self._df = coerce_to_dataframe(data).reset_index(drop=True)
        validate_columns(self._df, _REQUIRED_COLS)
        self.tech_indicator_list = list(tech_indicator_list or ["close"])
        validate_columns(self._df, self.tech_indicator_list)
        self.initial_amount = float(initial_amount)
        self.transaction_cost_pct = float(transaction_cost_pct)
        self.time_steps = max(1, int(time_steps))

        # Index by date for fast slicing; preserve original tic order.
        self._df = self._df.sort_values(["date", "tic"]).reset_index(drop=True)
        unique_dates = self._df["date"].unique()
        if len(unique_dates) <= self.time_steps + 1:
            raise ValueError(
                "PortfolioManagementEnv needs more than time_steps + 1 unique "
                f"dates; got {len(unique_dates)} with time_steps={self.time_steps}"
            )
        self._date_index = {d: i for i, d in enumerate(unique_dates)}
        self._dates = list(unique_dates)
        self.tics = list(self._df["tic"].unique())
        self.stock_dim = len(self.tics)

        # Pre-pivot for fast access: (T, F, N) tensors per indicator.
        self._features: dict[str, np.ndarray] = {}
        for col in self.tech_indicator_list:
            wide = self._df.pivot(index="date", columns="tic", values=col)
            wide = wide.reindex(columns=self.tics).ffill().bfill().fillna(0.0)
            self._features[col] = wide.to_numpy(dtype=np.float32)
        close_wide = self._df.pivot(index="date", columns="tic", values="close")
        close_wide = close_wide.reindex(columns=self.tics).ffill().bfill().fillna(0.0)
        self._close = close_wide.to_numpy(dtype=np.float32)

        f = len(self.tech_indicator_list)
        n = self.stock_dim
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(f, n, self.time_steps),
            dtype=np.float32,
        )
        # Action is a cash + N-ticker softmax weight vector.
        self.action_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(n + 1,),
            dtype=np.float32,
        )
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------ state

    def _reset_state(self) -> None:
        self.day_idx = self.time_steps - 1
        self.portfolio_value = self.initial_amount
        self.weights = np.concatenate(
            [[1.0], np.zeros(self.stock_dim, dtype=np.float32)]
        ).astype(np.float32)
        self.history = [self.portfolio_value]
        self.weight_history: list[np.ndarray] = [self.weights.copy()]

    def _obs(self) -> np.ndarray:
        start = self.day_idx - self.time_steps + 1
        end = self.day_idx + 1
        slices = [
            self._features[col][start:end, :].T  # (N, T)
            for col in self.tech_indicator_list
        ]
        tensor = np.stack(slices, axis=0).astype(np.float32)
        # Reshape to (F, N, T)
        return tensor

    # ------------------------------------------------------------------ gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), stamp_step_info(
            {},
            portfolio_value=self.portfolio_value,
            nav_return=0.0,
            t=self.day_idx,
            extras={
                "weights": self.weights.copy(),
                "stock_dim": self.stock_dim,
            },
        )

    def step(self, action: np.ndarray):
        terminated = self.day_idx >= len(self._dates) - 1
        if terminated:
            info = stamp_step_info(
                {},
                portfolio_value=self.portfolio_value,
                nav_return=0.0,
                t=self.day_idx,
                extras={"weights": self.weights.copy(), "terminated": True},
            )
            return self._obs(), 0.0, True, False, info

        action_arr = np.asarray(action, dtype=np.float32).flatten()
        if action_arr.size != self.stock_dim + 1:
            action_arr = np.resize(action_arr, (self.stock_dim + 1,)).astype(np.float32)
        # Soft renormalisation: if the action sums to 1 within tolerance and is
        # non-negative, accept it as-is; else softmax-fallback so the policy
        # can emit unnormalised logits.
        if float(action_arr.min()) >= -1e-6 and abs(float(action_arr.sum()) - 1.0) < 1e-6:
            target_weights = np.maximum(action_arr, 0.0)
            target_weights = target_weights / max(float(target_weights.sum()), 1e-9)
        else:
            target_weights = softmax_with_cash(action_arr)
        target_weights = target_weights.astype(np.float32)

        # Per-asset price ratios from t → t+1 (cash ratio = 1).
        prev_close = self._close[self.day_idx, :]
        self.day_idx += 1
        next_close = self._close[self.day_idx, :]
        # Guard against zero-prices.
        ratios_tickers = np.where(prev_close > 0, next_close / prev_close, 1.0)
        ratios = np.concatenate([[1.0], ratios_tickers]).astype(np.float64)

        # Realised portfolio return from holding the target weights through the bar.
        port_ratio = float(np.sum(target_weights * ratios))
        # Soft commission via weight-drift recalc.
        weights_drifted = normalise_weights(target_weights * ratios)
        turnover = float(np.sum(np.abs(self.weights - target_weights)))
        fee = self.transaction_cost_pct * self.portfolio_value * turnover
        prev_pv = self.portfolio_value
        self.portfolio_value = (self.portfolio_value - fee) * port_ratio
        nav_return = safe_pct_change(self.portfolio_value, prev_pv)
        reward = 0.0
        if prev_pv > 0 and self.portfolio_value > 0:
            reward = float(math.log(self.portfolio_value / prev_pv))

        self.weights = weights_drifted
        self.weight_history.append(self.weights.copy())
        self.history.append(self.portfolio_value)

        info: dict[str, Any] = {
            "weights": self.weights.copy(),
            "weights_brandnew": weights_drifted.copy(),
            "target_weights": target_weights.copy(),
            "turnover": turnover,
            "fee": float(fee),
        }
        stamp_step_info(
            info,
            portfolio_value=self.portfolio_value,
            nav_return=nav_return,
            t=self.day_idx,
        )
        return self._obs(), reward, False, False, info


__all__ = ["PortfolioManagementEnv"]
