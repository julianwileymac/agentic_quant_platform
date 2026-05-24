"""``OrderExecutionEnv`` — OPD-style teacher-student execution env.

Port of TradeMaster's
``trademaster/environments/order_execution/pd_environment.py`` into
AQP's :class:`BaseRLEnv` / metaclass conventions.

The env supports the OPD (Fang et al. AAAI 21) teacher-student
training pattern: the env stamps both the public (causal,
backward-looking) state and the "perfect" (future-aware) state into
``info`` so a teacher policy can train against the perfect window
while the student policy only consumes the public window. The
:class:`aqp_rl.agents` `OPDAgent` (Phase 4) reads these via
``info['perfect_state']`` and ``info['public_state']``.

Action space
============

``Box(0, 1, shape=(1,))`` — fraction of the *remaining* inventory the
agent commits to trade this step.

Observation
===========

Public imperfect state of shape ``(state_length, F)`` — F tech
indicators stacked over the most recent ``state_length`` bars.

Reward
======

Implementation-shortfall flavour::

    reward_t = action · (price_t / avg_price_so_far − 1)

Positive when the agent waits to sell into rising prices, negative
when it sells into falling prices. Terminal step liquidates the
remaining inventory unconditionally.
"""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent
from aqp_rl.envs.tradesim_base import (
    coerce_to_dataframe,
    safe_pct_change,
    stamp_step_info,
    validate_columns,
)

logger = logging.getLogger(__name__)


_REQUIRED_COLS = ("close",)


class OrderExecutionEnv(gym.Env, RLComponent):
    """OPD-style order-execution env with teacher-student dual state.

    Parameters
    ----------
    data:
        DataFrame (or :class:`BaseDataset`) with at minimum a ``close``
        column. ``tech_indicator_list`` columns are stacked into the
        observation.
    initial_amount:
        Starting cash. Default ``100_000``.
    state_length:
        Window of historical bars stacked into each observation.
        Default ``10``.
    tech_indicator_list:
        Column names that form the per-step observation vector.
    target_order:
        Total inventory size to liquidate (normalised to 1.0 internally).
        Default ``1``.
    teacher_lookahead:
        Extra forward bars the *teacher* policy sees as the "perfect"
        state. Default equals ``state_length``.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "tradesim_execution"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "order_execution"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "opd",
        "execution",
        "teacher_student",
        "implementation_shortfall",
    )

    def __init__(
        self,
        *,
        data: Any,
        initial_amount: float = 100_000.0,
        state_length: int = 10,
        tech_indicator_list: list[str] | None = None,
        target_order: float = 1.0,
        teacher_lookahead: int | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self._df = coerce_to_dataframe(data).reset_index(drop=True)
        validate_columns(self._df, _REQUIRED_COLS)
        self.tech_indicator_list = list(tech_indicator_list or ["close"])
        validate_columns(self._df, self.tech_indicator_list)
        self.initial_amount = float(initial_amount)
        self.state_length = int(state_length)
        self.target_order = float(target_order)
        self.teacher_lookahead = int(
            teacher_lookahead if teacher_lookahead is not None else state_length
        )
        n_rows = len(self._df)
        if n_rows <= self.state_length + self.teacher_lookahead + 1:
            raise ValueError(
                "OrderExecutionEnv data is too short — need at least "
                f"state_length ({self.state_length}) + teacher_lookahead "
                f"({self.teacher_lookahead}) + 2 rows; got {n_rows}"
            )

        feature_dim = len(self.tech_indicator_list)
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.state_length, feature_dim),
            dtype=np.float32,
        )
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------ state

    def _reset_state(self) -> None:
        self.day = self.state_length
        self.cash = self.initial_amount
        # Inventory normalised to [0, 1] — fraction of original target_order
        # still to be sold.
        self.inventory_frac = 1.0
        self.time_left_frac = 1.0
        self.history: list[float] = [self.initial_amount]
        self.fill_prices: list[float] = []
        self.action_history: list[float] = []
        self._initial_close = float(self._df["close"].iloc[self.day - 1])

    def _public_state(self) -> np.ndarray:
        start = self.day - self.state_length
        slc = self._df.iloc[start : self.day]
        return slc[self.tech_indicator_list].to_numpy(dtype=np.float32)

    def _perfect_state(self) -> np.ndarray:
        end = min(self.day + self.teacher_lookahead, len(self._df))
        start = self.day - self.state_length
        slc = self._df.iloc[start:end]
        return slc[self.tech_indicator_list].to_numpy(dtype=np.float32)

    def _private_state(self) -> np.ndarray:
        return np.asarray(
            [self.time_left_frac, self.inventory_frac],
            dtype=np.float32,
        )

    def _build_info(self, *, terminated: bool, fill_price: float, fill_qty: float) -> dict[str, Any]:
        avg_price_so_far = float(np.mean(self.fill_prices)) if self.fill_prices else self._initial_close
        info: dict[str, Any] = {
            "perfect_state": self._perfect_state(),
            "private_state": self._private_state(),
            "public_state": self._public_state(),
            "fill_price": float(fill_price),
            "arrival_price": float(self._initial_close),
            "executed_shares": float(fill_qty),
            "total_shares": float(self.target_order),
            "money_sold": float(self.cash - self.initial_amount + self.target_order * self._initial_close),
            "inventory": float(self.inventory_frac * self.target_order),
            "time_left": float(self.time_left_frac),
            "avg_price_so_far": avg_price_so_far,
            "is_terminal": bool(terminated),
            "terminated": bool(terminated),
        }
        return info

    # ------------------------------------------------------------------ gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        obs = self._public_state()
        info = self._build_info(terminated=False, fill_price=self._initial_close, fill_qty=0.0)
        stamp_step_info(
            info,
            portfolio_value=self.cash,
            nav_return=0.0,
            t=self.day,
        )
        return obs, info

    def step(self, action: np.ndarray):
        action_val = float(np.clip(np.asarray(action).flatten()[0], 0.0, 1.0))
        self.action_history.append(action_val)
        max_t = len(self._df) - 1
        terminated = self.day >= max_t

        current_price = float(self._df["close"].iloc[self.day])
        avg_price = float(np.mean(self.fill_prices)) if self.fill_prices else current_price

        if terminated:
            # Final liquidation — sell whatever remains at current price.
            qty = self.inventory_frac * self.target_order
            proceeds = qty * current_price
            self.cash += proceeds
            self.fill_prices.append(current_price)
            self.inventory_frac = 0.0
            self.time_left_frac = 0.0
            reward = float(qty * (current_price / avg_price - 1.0)) if avg_price > 0 else 0.0
            prev_pv = self.history[-1]
            self.history.append(self.cash)
            info = self._build_info(terminated=True, fill_price=current_price, fill_qty=qty)
            stamp_step_info(
                info,
                portfolio_value=self.cash,
                nav_return=safe_pct_change(self.cash, prev_pv),
                t=self.day,
            )
            return self._public_state(), reward, True, False, info

        # Non-terminal step: trade min(action · remaining, remaining).
        target_qty = action_val * self.inventory_frac * self.target_order
        # Hard cap at remaining.
        trade_qty = min(target_qty, self.inventory_frac * self.target_order)
        proceeds = trade_qty * current_price
        self.cash += proceeds
        if trade_qty > 0:
            self.fill_prices.append(current_price)
        self.inventory_frac = max(0.0, self.inventory_frac - (trade_qty / max(self.target_order, 1e-9)))

        # Advance time fraction (uniformly).
        remaining_steps = max_t - self.day
        if remaining_steps > 0:
            self.time_left_frac = max(0.0, self.time_left_frac - 1.0 / max(remaining_steps + 1, 1))
        self.day += 1

        # Reward: trade_qty · (current / avg - 1) — positive when selling above avg.
        reward = float(trade_qty * (current_price / max(avg_price, 1e-9) - 1.0))
        prev_pv = self.history[-1]
        self.history.append(self.cash)
        info = self._build_info(terminated=False, fill_price=current_price, fill_qty=trade_qty)
        stamp_step_info(
            info,
            portfolio_value=self.cash,
            nav_return=safe_pct_change(self.cash, prev_pv),
            t=self.day,
        )
        return self._public_state(), reward, False, False, info


__all__ = ["OrderExecutionEnv"]
