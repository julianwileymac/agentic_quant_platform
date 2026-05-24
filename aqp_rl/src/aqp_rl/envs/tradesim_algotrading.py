"""``AlgorithmicTradingEnv`` — single-asset discrete-volume hindsight env.

Port of TradeMaster's
``trademaster/environments/algorithmic_trading/environment.py`` into
AQP's :class:`BaseRLEnv` / metaclass conventions, plus the canonical
Gymnasium 5-tuple step contract and a BaseDataset-friendly data path
(no direct ``pd.read_csv``).

Action space
============

``Discrete(2 · max_volume + 1)`` — integer ``a ∈ {0, …, 2·max_volume}``
maps to a signed position delta ``buy_volume = a − max_volume`` in
``[−max_volume, +max_volume]``.

Observation
===========

Flat ``(F · backward_num_day + 2,)`` vector — ``F`` technical
indicators stacked over the last ``backward_num_day`` bars, plus
``[cash, holding]`` appended at the tail. Matches DeepScalper's
canonical input shape.

Reward
======

The default reward is DeepScalper's *hindsight* contribution::

    reward_t = holding · ((p_{t+1} − p_t) + λ · (p_{t+k} − p_t))

with ``k = forward_num_day`` and ``λ = future_weights``. The reward
is exposed as ``info`` keys (``position``, ``current_price``,
``next_price``, ``future_price``) so the registered reward term
:class:`aqp_rl.rewards.hindsight.HindsightReward` can compute it
explicitly via :class:`CompositeReward`; the env's default
``step`` driver computes the same scalar inline when no external
``reward_model`` is wired through the spec.
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


class AlgorithmicTradingEnv(gym.Env, RLComponent):
    """Single-asset RL env with DeepScalper-style hindsight reward.

    Parameters
    ----------
    data:
        Pandas DataFrame OR :class:`aqp.data.datasets.BaseDataset`
        instance OR ``dict`` of column-arrays. Must expose ``close``
        and every column listed in ``tech_indicator_list``.
    initial_amount:
        Starting cash. Default ``100_000``.
    transaction_cost_pct:
        Per-trade fraction subtracted from cash. Default ``0.001``.
    tech_indicator_list:
        Column names that form the per-step observation vector.
    backward_num_day:
        Number of historical bars stacked into each observation.
    forward_num_day:
        Hindsight lookahead window for the bonus reward term.
    max_volume:
        Maximum integer shares the agent can trade in one step.
    future_weights:
        ``λ`` multiplier on the hindsight PnL contribution.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "tradesim_algotrading"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "algorithmic_trading"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "deepscalper",
        "single_asset",
        "hindsight",
        "discrete_volume",
    )

    def __init__(
        self,
        *,
        data: Any,
        initial_amount: float = 100_000.0,
        transaction_cost_pct: float = 0.001,
        tech_indicator_list: list[str] | None = None,
        backward_num_day: int = 5,
        forward_num_day: int = 5,
        max_volume: int = 1,
        future_weights: float = 0.2,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self._df = coerce_to_dataframe(data).reset_index(drop=True)
        self.tech_indicator_list = list(tech_indicator_list or ["close"])
        validate_columns(self._df, [*_REQUIRED_COLS, *self.tech_indicator_list])
        self.initial_amount = float(initial_amount)
        self.transaction_cost_pct = float(transaction_cost_pct)
        self.backward_num_day = int(backward_num_day)
        self.forward_num_day = int(forward_num_day)
        self.max_volume = int(max_volume)
        self.future_weights = float(future_weights)

        n_rows = len(self._df)
        if n_rows <= self.backward_num_day + self.forward_num_day + 1:
            raise ValueError(
                "AlgorithmicTradingEnv data is too short — need at least "
                f"backward_num_day ({self.backward_num_day}) + "
                f"forward_num_day ({self.forward_num_day}) + 2 rows; "
                f"got {n_rows}"
            )

        feature_dim = len(self.tech_indicator_list) * self.backward_num_day + 2
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(feature_dim,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(2 * self.max_volume + 1)
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------ state

    def _reset_state(self) -> None:
        self.t = self.backward_num_day
        self.cash = self.initial_amount
        self.position: int = 0
        self.portfolio_value = self.initial_amount
        self._initial_close = float(self._df["close"].iloc[self.t])
        self.history: list[float] = [self.portfolio_value]

    def _features_block(self, end_idx: int) -> np.ndarray:
        """Tech-indicator slice of shape ``(F, backward_num_day)`` flattened."""
        start_idx = max(0, end_idx - self.backward_num_day)
        slc = self._df.iloc[start_idx:end_idx]
        parts: list[np.ndarray] = []
        for col in self.tech_indicator_list:
            values = slc[col].to_numpy(dtype=np.float32)
            if values.shape[0] < self.backward_num_day:
                pad = np.zeros(self.backward_num_day - values.shape[0], dtype=np.float32)
                values = np.concatenate([pad, values])
            parts.append(values)
        return np.concatenate(parts).astype(np.float32)

    def _obs(self) -> np.ndarray:
        feats = self._features_block(self.t)
        tail = np.asarray([self.cash, self.position], dtype=np.float32)
        return np.concatenate([feats, tail]).astype(np.float32)

    def _close(self, idx: int) -> float:
        return float(self._df["close"].iloc[max(0, min(idx, len(self._df) - 1))])

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
            t=self.t,
            extras={"position": self.position, "cash": self.cash},
        )

    def step(self, action: int):
        max_t = len(self._df) - self.forward_num_day - 1
        terminated = self.t >= max_t

        # Decode discrete action into signed volume in [-max_volume, +max_volume].
        buy_volume = int(action) - self.max_volume

        if not terminated:
            new_holding = self.position + buy_volume
            current_price = self._close(self.t)
            # Cash bookkeeping with transaction cost.
            if buy_volume == 0:
                pass  # no trade
            elif buy_volume < 0:
                # Selling: receive cash net of fee.
                self.cash += abs(buy_volume) * current_price * (1 - self.transaction_cost_pct)
                self.position = new_holding
            else:
                # Buying: pay cash + fee. If we can't afford, clamp to the
                # maximum integer we can buy.
                gross = buy_volume * current_price / (1 - self.transaction_cost_pct)
                if self.cash >= gross:
                    self.cash -= gross
                    self.position = new_holding
                else:
                    max_buy = int(self.cash / (current_price / (1 - self.transaction_cost_pct)))
                    if max_buy > 0:
                        self.cash -= max_buy * current_price / (1 - self.transaction_cost_pct)
                        self.position += max_buy
                    # Else: trade rejected silently.

            # Advance time.
            old_price = current_price
            self.t += 1
            new_price = self._close(self.t)
            future_price = self._close(self.t + self.forward_num_day - 1)

            # Hindsight reward — bypassed when an external reward_model
            # is wired in (the consumer composes via info["reward_terms"]).
            reward = float(
                self.position * ((new_price - old_price) + self.future_weights * (future_price - old_price))
            )
            prev_pv = self.portfolio_value
            self.portfolio_value = self.cash + self.position * new_price
            nav_return = safe_pct_change(self.portfolio_value, prev_pv)
            self.history.append(self.portfolio_value)

            info: dict[str, Any] = {
                "position": int(self.position),
                "cash": float(self.cash),
                "current_price": float(old_price),
                "next_price": float(new_price),
                "future_price": float(future_price),
                "executed_shares": int(buy_volume),
                "arrival_price": float(self._initial_close),
                "fill_price": float(old_price),
                "total_shares": self.max_volume,
            }
            stamp_step_info(
                info,
                portfolio_value=self.portfolio_value,
                nav_return=nav_return,
                t=self.t,
            )
            return self._obs(), reward, False, False, info

        # Terminal step — flatten and emit a final reward.
        final_price = self._close(self.t)
        if self.position != 0:
            self.cash += self.position * final_price * (1 - self.transaction_cost_pct)
            self.position = 0
        prev_pv = self.portfolio_value
        self.portfolio_value = self.cash
        nav_return = safe_pct_change(self.portfolio_value, prev_pv)
        self.history.append(self.portfolio_value)
        info = {
            "position": 0,
            "cash": float(self.cash),
            "current_price": float(final_price),
            "next_price": float(final_price),
            "future_price": float(final_price),
            "executed_shares": 0,
            "arrival_price": float(self._initial_close),
            "fill_price": float(final_price),
            "total_shares": self.max_volume,
            "terminated": True,
        }
        stamp_step_info(
            info,
            portfolio_value=self.portfolio_value,
            nav_return=nav_return,
            t=self.t,
        )
        return self._obs(), 0.0, True, False, info


__all__ = ["AlgorithmicTradingEnv"]
