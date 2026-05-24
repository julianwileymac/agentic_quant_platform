"""``MultimodalTradingEnv`` — FinAgent-style multimodal trading env.

Port of TradeMaster's ``finagent/environment/trading.py`` shape into
AQP's :class:`BaseRLEnv` / metaclass conventions, with the canonical
Gymnasium 5-tuple step.

Action space
============

``Discrete(3)`` — ``{0: SELL, 1: HOLD, 2: BUY}``. Mapped internally
to position deltas in ``[−1, 0, +1]`` after subtracting an offset.

Observation
===========

``gym.spaces.Dict`` with five named slices (matches the FinAgent
``EnvironmentTrading.get_state`` contract):

- ``price`` — ``(L, F_price)`` matrix of recent price bars.
- ``news`` — ``(L_news, D_news)`` matrix of news embeddings (zeros
  when ``news_df`` is absent).
- ``sentiment`` — ``(L_sent, D_sent)`` matrix of sentiment scores
  (zeros when absent).
- ``guidance`` — ``(L_guide, D_guide)`` matrix of company-guidance
  embeddings (zeros when absent).
- ``economic`` — ``(L_econ, D_econ)`` matrix of macro/economic
  indicators (zeros when absent).

This env's primary consumer is the layered FinAgent LLM-hybrid agent
(Phase 10) which constructs prompts from these named slices via a
chart-plotting tool. A vanilla RL adapter can flatten the dict
observation if it needs a single vector input.

Reward
======

Per-step portfolio return ``(post_value − pre_value) / pre_value``
with a configurable ``discount`` factor applied to the cumulative
return so the env mirrors FinAgent's reward shape.
"""
from __future__ import annotations

import logging
from datetime import datetime
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

_PRICE_COLS = ("open", "high", "low", "close", "adj_close")
_ACTION_MAP = {0: -1, 1: 0, 2: 1}  # SELL, HOLD, BUY


class MultimodalTradingEnv(gym.Env, RLComponent):
    """Multimodal single-asset trading env for FinAgent-style LLM agents.

    Parameters
    ----------
    price_data:
        DataFrame (or BaseDataset) with one row per bar; must include
        ``adj_close`` (used as the trading price). When ``adj_close``
        is missing the env falls back to ``close``.
    news_data, sentiment_data, guidance_data, economic_data:
        Optional DataFrames keyed on timestamp. Each is sliced into
        the per-step observation window.
    selected_asset, asset_type:
        Free-form symbol + asset-class labels surfaced into ``info``.
    look_back_days, look_forward_days:
        Window sizes for the observation slices and (for the
        teacher-style training mode) the future-aware peek.
    initial_amount:
        Starting cash.
    transaction_cost_pct:
        Per-trade fee fraction.
    discount:
        Per-step decay applied to cumulative return.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "finagent_trading"
    rl_source: ClassVar[str] = "finagent"
    rl_category: ClassVar[str] = "multimodal_trading"
    rl_tags: ClassVar[tuple[str, ...]] = (
        "multimodal",
        "finagent",
        "llm",
        "dict_observation",
    )

    def __init__(
        self,
        *,
        price_data: Any,
        news_data: Any | None = None,
        sentiment_data: Any | None = None,
        guidance_data: Any | None = None,
        economic_data: Any | None = None,
        selected_asset: str = "AAPL",
        asset_type: str = "company",
        look_back_days: int = 14,
        look_forward_days: int = 14,
        initial_amount: float = 1e4,
        transaction_cost_pct: float = 1e-3,
        discount: float = 1.0,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.price_df = coerce_to_dataframe(price_data).reset_index(drop=True)
        if "adj_close" not in self.price_df.columns and "close" in self.price_df.columns:
            self.price_df = self.price_df.assign(adj_close=self.price_df["close"])
        validate_columns(self.price_df, ["adj_close"])

        self.news_df = (
            coerce_to_dataframe(news_data).reset_index(drop=True) if news_data is not None else None
        )
        self.sentiment_df = (
            coerce_to_dataframe(sentiment_data).reset_index(drop=True)
            if sentiment_data is not None
            else None
        )
        self.guidance_df = (
            coerce_to_dataframe(guidance_data).reset_index(drop=True)
            if guidance_data is not None
            else None
        )
        self.economic_df = (
            coerce_to_dataframe(economic_data).reset_index(drop=True)
            if economic_data is not None
            else None
        )

        self.selected_asset = str(selected_asset)
        self.asset_type = str(asset_type)
        self.look_back_days = max(1, int(look_back_days))
        self.look_forward_days = max(1, int(look_forward_days))
        self.initial_amount = float(initial_amount)
        self.transaction_cost_pct = float(transaction_cost_pct)
        self.discount_factor = float(discount)

        n_rows = len(self.price_df)
        if n_rows <= self.look_back_days + 1:
            raise ValueError(
                "MultimodalTradingEnv price_data is too short — need at least "
                f"look_back_days ({self.look_back_days}) + 2 rows; got {n_rows}"
            )

        price_features = [c for c in _PRICE_COLS if c in self.price_df.columns]
        self._price_feature_cols = price_features

        # Build the Dict observation space. We declare reasonable shapes
        # for non-price slices; per-slice arrays are zero-filled when the
        # source DataFrame is missing.
        self.observation_space = spaces.Dict(
            {
                "price": spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(self.look_back_days, max(len(price_features), 1)),
                    dtype=np.float32,
                ),
                "news": spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(self.look_back_days, max(self._embed_dim(self.news_df), 1)),
                    dtype=np.float32,
                ),
                "sentiment": spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(self.look_back_days, max(self._embed_dim(self.sentiment_df), 1)),
                    dtype=np.float32,
                ),
                "guidance": spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(self.look_back_days, max(self._embed_dim(self.guidance_df), 1)),
                    dtype=np.float32,
                ),
                "economic": spaces.Box(
                    low=-np.inf,
                    high=np.inf,
                    shape=(self.look_back_days, max(self._embed_dim(self.economic_df), 1)),
                    dtype=np.float32,
                ),
            }
        )
        self.action_space = spaces.Discrete(3)
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _embed_dim(df: pd.DataFrame | None) -> int:
        if df is None:
            return 1
        # Number of float-like columns (excluding any timestamp / symbol).
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        return len(numeric) if numeric else 1

    def _slice_numeric(self, df: pd.DataFrame | None, *, target_dim: int) -> np.ndarray:
        if df is None:
            return np.zeros((self.look_back_days, target_dim), dtype=np.float32)
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if not numeric:
            return np.zeros((self.look_back_days, target_dim), dtype=np.float32)
        start = max(0, self.day - self.look_back_days)
        slc = df.iloc[start : self.day][numeric]
        arr = slc.to_numpy(dtype=np.float32)
        if arr.shape[0] < self.look_back_days:
            pad = np.zeros((self.look_back_days - arr.shape[0], arr.shape[1]), dtype=np.float32)
            arr = np.concatenate([pad, arr], axis=0)
        # Pad / truncate column dim to ``target_dim``.
        if arr.shape[1] < target_dim:
            pad = np.zeros((arr.shape[0], target_dim - arr.shape[1]), dtype=np.float32)
            arr = np.concatenate([arr, pad], axis=1)
        elif arr.shape[1] > target_dim:
            arr = arr[:, :target_dim]
        return arr

    # ------------------------------------------------------------------ state

    def _reset_state(self) -> None:
        self.day = self.look_back_days
        self.cash = self.initial_amount
        self.position: int = 0
        self.value = self.initial_amount
        self.discount = 1.0
        self.total_return = 0.0
        self.last_action = "HOLD"
        self.history: list[float] = [self.value]

    def _current_price(self) -> float:
        return float(self.price_df["adj_close"].iloc[self.day])

    def _obs(self) -> dict[str, np.ndarray]:
        price_arr = self.price_df.iloc[
            max(0, self.day - self.look_back_days) : self.day
        ][self._price_feature_cols or ["adj_close"]].to_numpy(dtype=np.float32)
        if price_arr.shape[0] < self.look_back_days:
            pad = np.zeros(
                (self.look_back_days - price_arr.shape[0], price_arr.shape[1]),
                dtype=np.float32,
            )
            price_arr = np.concatenate([pad, price_arr], axis=0)
        return {
            "price": price_arr.astype(np.float32),
            "news": self._slice_numeric(
                self.news_df, target_dim=self.observation_space["news"].shape[1]
            ),
            "sentiment": self._slice_numeric(
                self.sentiment_df,
                target_dim=self.observation_space["sentiment"].shape[1],
            ),
            "guidance": self._slice_numeric(
                self.guidance_df,
                target_dim=self.observation_space["guidance"].shape[1],
            ),
            "economic": self._slice_numeric(
                self.economic_df,
                target_dim=self.observation_space["economic"].shape[1],
            ),
        }

    # ------------------------------------------------------------------ trading

    def _max_buy_shares(self, price: float) -> int:
        if price <= 0:
            return 0
        return int(self.cash / (price * (1 + self.transaction_cost_pct)))

    def _buy(self, price: float) -> None:
        n = self._max_buy_shares(price)
        if n <= 0:
            self.last_action = "HOLD"
            return
        self.cash -= n * price * (1 + self.transaction_cost_pct)
        self.position += n
        self.last_action = "BUY"

    def _sell(self, price: float) -> None:
        if self.position <= 0:
            self.last_action = "HOLD"
            return
        self.cash += self.position * price * (1 - self.transaction_cost_pct)
        self.position = 0
        self.last_action = "SELL"

    # ------------------------------------------------------------------ gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        info = self._build_info(action_label="HOLD", reward=0.0)
        return self._obs(), info

    def step(self, action: int):
        action_int = _ACTION_MAP.get(int(action), 0)
        price = self._current_price()
        pre_value = self.value

        if action_int > 0:
            self._buy(price)
        elif action_int < 0:
            self._sell(price)
        else:
            self.last_action = "HOLD"

        # Advance time.
        self.day += 1
        terminated = self.day >= len(self.price_df) - 1
        next_price = (
            float(self.price_df["adj_close"].iloc[self.day])
            if not terminated
            else price
        )
        self.value = self.cash + self.position * next_price
        reward = safe_pct_change(self.value, pre_value)
        self.total_return += self.discount * reward
        self.discount *= self.discount_factor
        self.history.append(self.value)

        info = self._build_info(action_label=self.last_action, reward=reward)
        return self._obs(), float(reward), bool(terminated), False, info

    def _build_info(self, *, action_label: str, reward: float) -> dict[str, Any]:
        price = self._current_price()
        info: dict[str, Any] = {
            "symbol": self.selected_asset,
            "asset_type": self.asset_type,
            "cash": float(self.cash),
            "position": int(self.position),
            "price": float(price),
            "ret": float(reward),
            "total_return": float(self.total_return),
            "action": action_label,
        }
        stamp_step_info(
            info,
            portfolio_value=float(self.value),
            nav_return=float(reward),
            t=self.day,
        )
        return info


__all__ = ["MultimodalTradingEnv"]
