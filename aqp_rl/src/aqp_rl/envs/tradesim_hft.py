"""``HighFrequencyTradingEnv`` — LOB-stacked HFT env with DP demonstration.

Port of TradeMaster's
``trademaster/environments/high_frequency_trading/environment.py``
into AQP's :class:`BaseRLEnv` / metaclass conventions.

Action space
============

``Discrete(num_action)`` — typically ``num_action=11`` representing
position fractions ``a / (num_action - 1) ∈ {0, 0.1, …, 1.0}`` of the
``max_holding_number`` cap.

Observation
===========

Flat ``(F · stack_length,)`` vector of LOB features stacked over the
``stack_length`` most recent ticks.

DP demonstration
================

At ``__init__`` time the env runs the multi-level DP oracle from
TradeMaster — full lookahead through the entire price path computes
the position-vs-time trajectory that maximises terminal PnL given the
real bid/ask depth. ``info["DP_action"]`` is a one-hot of that
oracle's choice at the current tick; the
:class:`aqp_rl.rewards.dp_distillation.DPDistillation` reward + the
HFT_DDQN agent's KL loss use it to regularise the agent toward
oracle behaviour.

Available-action masking
========================

``info["available_action"]`` is a 0/1 vector of length ``num_action``
that the agent's policy network can apply as a logit mask
(``logits + (mask - 1) · max_punish``) — TradeMaster's
``HFTQNet`` does this internally; we expose the mask so any
masked-action SB3 wrapper or custom agent can apply it.
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


_REQUIRED_BID_COLS = tuple(f"bid{i}_price" for i in range(1, 6)) + tuple(
    f"bid{i}_size" for i in range(1, 6)
)
_REQUIRED_ASK_COLS = tuple(f"ask{i}_price" for i in range(1, 6)) + tuple(
    f"ask{i}_size" for i in range(1, 6)
)


class HighFrequencyTradingEnv(gym.Env, RLComponent):
    """LOB-stacked HFT env with multi-level DP demonstration oracle.

    Parameters
    ----------
    data:
        DataFrame (or :class:`BaseDataset`) with 5-level bid/ask LOB
        columns: ``bid1_price..bid5_price``, ``bid1_size..bid5_size``,
        ``ask1_price..ask5_price``, ``ask1_size..ask5_size``.
        ``tech_indicator_list`` columns are stacked into the
        observation.
    tech_indicator_list:
        Column names that form the per-step observation vector.
    stack_length:
        Number of historical ticks stacked into each observation.
    transaction_cost_pct:
        Per-trade fee fraction. Default ``5e-5`` (matches Binance
        spot maker fee).
    max_holding_number:
        Inventory cap (absolute units). Default ``0.01``.
    num_action:
        Number of discrete position levels (including 0 and max).
        Default ``11`` ⇒ steps of 10%.
    max_punish:
        Logit offset for masked actions. Surfaces in
        ``info['max_punish']`` so the agent can apply ``logits +
        (mask - 1) · max_punish`` to invalid actions.
    enable_dp_oracle:
        Build the DP demonstration array at init. Default ``True``.
        Set ``False`` for very long datasets where the O(num_action²
        · len(data)) DP table is too expensive at construction.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "tradesim_hft"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "high_frequency_trading"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "hft",
        "lob",
        "ddqn",
        "dp_demonstration",
        "action_mask",
    )

    def __init__(
        self,
        *,
        data: Any,
        tech_indicator_list: list[str] | None = None,
        stack_length: int = 1,
        transaction_cost_pct: float = 5e-5,
        max_holding_number: float = 0.01,
        num_action: int = 11,
        max_punish: float = 1e12,
        enable_dp_oracle: bool = True,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self._df = coerce_to_dataframe(data).reset_index(drop=True)
        validate_columns(self._df, [*_REQUIRED_BID_COLS, *_REQUIRED_ASK_COLS])
        self.tech_indicator_list = list(
            tech_indicator_list or list(_REQUIRED_BID_COLS) + list(_REQUIRED_ASK_COLS)
        )
        validate_columns(self._df, self.tech_indicator_list)
        self.stack_length = max(1, int(stack_length))
        self.transaction_cost_pct = float(transaction_cost_pct)
        self.max_holding_number = float(max_holding_number)
        self.num_action = int(num_action)
        self.max_punish = float(max_punish)
        self.enable_dp_oracle = bool(enable_dp_oracle)

        n_rows = len(self._df)
        if n_rows <= self.stack_length + 1:
            raise ValueError(
                "HighFrequencyTradingEnv data is too short — need at least "
                f"stack_length ({self.stack_length}) + 2 rows; got {n_rows}"
            )

        feature_dim = len(self.tech_indicator_list) * self.stack_length
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(feature_dim,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(self.num_action)
        self._rng = np.random.default_rng(seed)

        if self.enable_dp_oracle:
            self._dp_actions = self._compute_dp_demonstration()
        else:
            self._dp_actions = np.zeros(n_rows, dtype=np.int64)

        self._reset_state()

    # ------------------------------------------------------------------ state

    def _reset_state(self) -> None:
        self.t = self.stack_length
        self.position: float = 0.0
        self.previous_action: int = 0
        self.cash: float = 0.0
        self.commission_paid: float = 0.0
        self.history: list[float] = [0.0]

    def _portfolio_value(self) -> float:
        bid1 = float(self._df["bid1_price"].iloc[min(self.t, len(self._df) - 1)])
        return float(self.cash + self.position * bid1)

    def _features_block(self) -> np.ndarray:
        start = self.t - self.stack_length
        slc = self._df.iloc[start : self.t]
        return slc[self.tech_indicator_list].to_numpy(dtype=np.float32).flatten()

    def _available_mask(self, row: pd.Series) -> np.ndarray:
        """Discrete-action mask: which positions are reachable from current state.

        Accounts for the limited bid/ask depth — the agent cannot
        execute a position change larger than the cumulative size of
        the 4 best levels.
        """
        buy_size = float(
            row.get("ask1_size", 0) + row.get("ask2_size", 0)
            + row.get("ask3_size", 0) + row.get("ask4_size", 0)
        )
        sell_size = float(
            row.get("bid1_size", 0) + row.get("bid2_size", 0)
            + row.get("bid3_size", 0) + row.get("bid4_size", 0)
        )
        position_upper = min(self.position + buy_size, self.max_holding_number)
        position_lower = max(self.position - sell_size, 0.0)
        scale = (self.num_action - 1) / max(self.max_holding_number, 1e-9)
        action_upper = int(position_upper * scale)
        action_lower = int(position_lower * scale) if position_lower > 0 else 0
        mask = np.zeros(self.num_action, dtype=np.int8)
        if action_lower <= action_upper:
            mask[action_lower : action_upper + 1] = 1
        else:
            mask[: action_upper + 1] = 1
        return mask

    def _sell_value(self, row: pd.Series, size: float) -> tuple[float, float]:
        """Walk through bid depth and return (cash_in, actual_size_sold)."""
        remaining = size
        cash_in = 0.0
        for i in range(1, 6):
            depth = float(row.get(f"bid{i}_size", 0))
            price = float(row.get(f"bid{i}_price", 0))
            if remaining <= depth:
                cash_in += price * remaining
                remaining = 0.0
                break
            cash_in += price * depth
            remaining -= depth
        actual = size - remaining
        fee = self.transaction_cost_pct * cash_in
        self.commission_paid += fee
        return cash_in - fee, actual

    def _buy_value(self, row: pd.Series, size: float) -> tuple[float, float]:
        """Walk through ask depth and return (cash_out, actual_size_bought)."""
        remaining = size
        cash_out = 0.0
        for i in range(1, 6):
            depth = float(row.get(f"ask{i}_size", 0))
            price = float(row.get(f"ask{i}_price", 0))
            if remaining <= depth:
                cash_out += price * remaining
                remaining = 0.0
                break
            cash_out += price * depth
            remaining -= depth
        actual = size - remaining
        fee = self.transaction_cost_pct * cash_out
        self.commission_paid += fee
        return cash_out + fee, actual

    def _compute_dp_demonstration(self) -> np.ndarray:
        """Multi-level dynamic-programming oracle (forward-aware optimum).

        Returns a length-``len(df)`` array of optimal-action integers
        in ``[0, num_action - 1]``. Memory complexity is
        ``O(len(df) · num_action)`` so this is fine for moderate
        datasets (1e5 rows × 11 actions = 1e6 entries).
        """
        n = len(self._df)
        dp = np.zeros((n, self.num_action), dtype=np.float64)
        backptr = np.zeros((n, self.num_action), dtype=np.int64)
        scale = (self.num_action - 1) / max(self.max_holding_number, 1e-9)

        # Pre-extract LOB arrays for speed.
        bid_p = self._df[[f"bid{i}_price" for i in range(1, 6)]].to_numpy(dtype=np.float64)
        bid_s = self._df[[f"bid{i}_size" for i in range(1, 6)]].to_numpy(dtype=np.float64)
        ask_p = self._df[[f"ask{i}_price" for i in range(1, 6)]].to_numpy(dtype=np.float64)
        ask_s = self._df[[f"ask{i}_size" for i in range(1, 6)]].to_numpy(dtype=np.float64)

        def cost_of_change(idx: int, delta_pos: float) -> float:
            """Return signed cash flow for changing position by ``delta_pos`` at ``idx``."""
            if delta_pos == 0:
                return 0.0
            if delta_pos > 0:
                # Buy ⇒ negative cash flow.
                remaining = delta_pos
                cash_out = 0.0
                for k in range(5):
                    depth = ask_s[idx, k]
                    if remaining <= depth:
                        cash_out += ask_p[idx, k] * remaining
                        remaining = 0
                        break
                    cash_out += ask_p[idx, k] * depth
                    remaining -= depth
                if remaining > 0:
                    return -1e9  # cannot fill — heavy penalty
                return -cash_out * (1 + self.transaction_cost_pct)
            # Sell ⇒ positive cash flow.
            remaining = -delta_pos
            cash_in = 0.0
            for k in range(5):
                depth = bid_s[idx, k]
                if remaining <= depth:
                    cash_in += bid_p[idx, k] * remaining
                    remaining = 0
                    break
                cash_in += bid_p[idx, k] * depth
                remaining -= depth
            if remaining > 0:
                return -1e9
            return cash_in * (1 - self.transaction_cost_pct)

        # Initialise from position 0 at t=0.
        for j in range(self.num_action):
            new_pos = j / scale
            dp[0, j] = cost_of_change(0, new_pos)

        # Forward DP.
        for t in range(1, n):
            for j in range(self.num_action):
                new_pos = j / scale
                best = -float("inf")
                best_k = 0
                for k in range(self.num_action):
                    old_pos = k / scale
                    cf = cost_of_change(t, new_pos - old_pos)
                    candidate = dp[t - 1, k] + cf
                    if candidate > best:
                        best = candidate
                        best_k = k
                dp[t, j] = best
                backptr[t, j] = best_k

        # Backtrack — terminal action is the one that maximises final cash.
        last_action = int(np.argmax(dp[n - 1]))
        actions = np.empty(n, dtype=np.int64)
        actions[n - 1] = last_action
        for t in range(n - 1, 0, -1):
            last_action = backptr[t, last_action]
            actions[t - 1] = last_action
        return actions

    # ------------------------------------------------------------------ gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        row = self._df.iloc[self.t - 1]
        mask = self._available_mask(row)
        dp_one_hot = np.zeros(self.num_action, dtype=np.int8)
        dp_one_hot[self._dp_actions[self.t - 1]] = 1
        info = {
            "previous_action": int(self.previous_action),
            "available_action": mask,
            "DP_action": dp_one_hot,
            "position": float(self.position),
            "cash": float(self.cash),
            "max_punish": float(self.max_punish),
        }
        stamp_step_info(
            info,
            portfolio_value=self._portfolio_value(),
            nav_return=0.0,
            t=self.t,
        )
        return self._features_block(), info

    def step(self, action: int):
        terminated = self.t >= len(self._df) - 1
        row = self._df.iloc[self.t]

        # Map discrete action to absolute target position.
        scale = (self.num_action - 1) / max(self.max_holding_number, 1e-9)
        target_pos = int(action) / scale
        delta = target_pos - self.position
        prev_pv = self._portfolio_value()

        if delta > 0:
            cash_out, actual = self._buy_value(row, delta)
            self.cash -= cash_out
            self.position += actual
        elif delta < 0:
            cash_in, actual = self._sell_value(row, -delta)
            self.cash += cash_in
            self.position -= actual
        # else: hold — no fills.

        self.previous_action = int(action)
        self.t += 1
        new_pv = self._portfolio_value()
        reward = float(new_pv - prev_pv)
        self.history.append(new_pv)

        if not terminated:
            next_row = self._df.iloc[self.t]
        else:
            next_row = row
        mask = self._available_mask(next_row)
        dp_idx = min(self.t, len(self._dp_actions) - 1)
        dp_one_hot = np.zeros(self.num_action, dtype=np.int8)
        dp_one_hot[self._dp_actions[dp_idx]] = 1

        info: dict[str, Any] = {
            "previous_action": int(self.previous_action),
            "available_action": mask,
            "DP_action": dp_one_hot,
            "position": float(self.position),
            "cash": float(self.cash),
            "max_punish": float(self.max_punish),
            "commission_paid": float(self.commission_paid),
        }
        stamp_step_info(
            info,
            portfolio_value=new_pv,
            nav_return=safe_pct_change(new_pv, prev_pv),
            t=self.t,
            extras={"terminated": terminated},
        )
        return self._features_block(), reward, terminated, False, info


__all__ = ["HighFrequencyTradingEnv"]
