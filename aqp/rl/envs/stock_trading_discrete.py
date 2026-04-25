"""Single-stock discrete buy/sell/hold env — the canonical FinRL NeurIPS
2018 setup (action in {0=hold, 1=buy N shares, 2=sell N shares}).

State is a compact bundle built from the bar window:

    [cash_normalized, position_shares_normalized, price_normalized,
     indicator_1, indicator_2, ..., return_1, return_5]

Reward is log-return of the portfolio with an optional transaction-cost
penalty and a small cash-idle penalty (FinRL's CashPenaltyEnv trick).

Plugs straight into the existing :class:`aqp.rl.agents.sb3_adapter.SB3Adapter`
via the shared registry — no separate trainer needed.
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp.core.registry import register
from aqp.rl.envs.base import load_bars, safe_array


_DEFAULT_INDICATORS = ("macd", "rsi_14", "sma_20", "sma_50")


@register("StockTradingDiscreteEnv")
class StockTradingDiscreteEnv(gym.Env):
    """FinRL-style single-stock discrete trading env.

    Parameters
    ----------
    symbol:
        The ticker (or ``ticker.exchange``) traded by the agent.
    start / end:
        ISO dates bounding the training window.
    initial_balance:
        Starting cash. Share count tracked separately.
    shares_per_trade:
        Number of shares bought/sold per BUY/SELL action.
    transaction_cost_pct:
        Cost as a fraction of notional per fill.
    indicators:
        Technical indicator columns to include in the observation.
    reward_scaling:
        Multiplier applied to the log-return reward.
    cash_penalty:
        Small negative reward per step when the agent is 100% cash
        (FinRL trick to discourage idle capital).
    """

    metadata = {"render_modes": ["human"]}

    HOLD, BUY, SELL = 0, 1, 2

    def __init__(
        self,
        symbol: str,
        start: str,
        end: str,
        *,
        initial_balance: float = 10000.0,
        shares_per_trade: int = 10,
        transaction_cost_pct: float = 0.001,
        indicators: list[str] | None = None,
        reward_scaling: float = 1.0,
        cash_penalty: float = 0.0005,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.symbol = symbol
        self.initial_balance = float(initial_balance)
        self.shares_per_trade = int(max(1, shares_per_trade))
        self.transaction_cost_pct = float(transaction_cost_pct)
        self.reward_scaling = float(reward_scaling)
        self.cash_penalty = float(cash_penalty)
        self.indicators = list(indicators or _DEFAULT_INDICATORS)

        bars = load_bars([symbol], start, end, indicators=self.indicators)
        if bars.empty:
            raise RuntimeError(
                f"StockTradingDiscreteEnv: no data for {symbol} in {start}..{end}."
            )
        # Single-stock env → pull the one vt_symbol's bars.
        vt = (bars["vt_symbol"].iloc[0]) if "vt_symbol" in bars.columns else f"{symbol}.NASDAQ"
        single = bars[bars["vt_symbol"] == vt].sort_values("timestamp").reset_index(drop=True)
        if len(single) < 2:
            raise RuntimeError(f"StockTradingDiscreteEnv: need at least 2 bars for {symbol}.")

        self.prices = single["close"].astype(float).values
        self.ret_1 = np.concatenate(
            [[0.0], np.diff(self.prices) / np.where(self.prices[:-1] == 0, 1.0, self.prices[:-1])]
        )
        self.ret_5 = np.concatenate(
            [[0.0] * 5, self.prices[5:] / self.prices[:-5] - 1.0]
        ) if len(self.prices) > 5 else np.zeros_like(self.prices)
        self.indicator_table = {
            name: single[name].astype(float).values
            if name in single.columns
            else np.zeros_like(self.prices)
            for name in self.indicators
        }

        self.horizon = len(self.prices)
        obs_dim = 3 + len(self.indicators) + 2  # cash, position, price + indicators + two returns
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(3)

        self._rng = np.random.default_rng(seed)
        self._reset_state()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        self.idx = 0
        self.cash = self.initial_balance
        self.shares = 0
        self.portfolio_value = self.initial_balance
        self.prev_value = self.initial_balance
        self.history: list[float] = [self.initial_balance]

    def _obs(self) -> np.ndarray:
        price = float(self.prices[self.idx])
        obs = [
            self.cash / self.initial_balance,
            float(self.shares * price) / self.initial_balance,
            price / self.initial_balance,
        ]
        for name in self.indicators:
            obs.append(float(self.indicator_table[name][self.idx]) / (1.0 + price))
        obs.append(float(self.ret_1[self.idx]))
        obs.append(float(self.ret_5[self.idx]))
        return safe_array(np.asarray(obs, dtype=np.float32))

    # ------------------------------------------------------------------
    # Gym API
    # ------------------------------------------------------------------

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: int):
        action = int(np.asarray(action).flatten()[0])
        price = float(self.prices[self.idx])
        cost = 0.0

        if action == self.BUY:
            notional = price * self.shares_per_trade
            fee = notional * self.transaction_cost_pct
            if self.cash >= notional + fee:
                self.cash -= notional + fee
                self.shares += self.shares_per_trade
                cost = fee
        elif action == self.SELL:
            if self.shares >= self.shares_per_trade:
                notional = price * self.shares_per_trade
                fee = notional * self.transaction_cost_pct
                self.cash += notional - fee
                self.shares -= self.shares_per_trade
                cost = fee

        # Advance a step and compute the new portfolio value.
        self.idx += 1
        done = self.idx >= self.horizon - 1
        new_price = float(self.prices[self.idx])
        self.portfolio_value = self.cash + self.shares * new_price

        prev = self.prev_value
        ret = 0.0
        if prev > 0:
            ret = (self.portfolio_value - prev) / prev
        reward = ret * self.reward_scaling
        if self.shares == 0 and self.cash_penalty > 0:
            reward -= self.cash_penalty
        self.prev_value = self.portfolio_value
        self.history.append(self.portfolio_value)

        info: dict[str, Any] = {
            "price": new_price,
            "cash": self.cash,
            "shares": self.shares,
            "portfolio_value": self.portfolio_value,
            "cost": cost,
            "action": int(action),
        }
        return self._obs(), float(reward), bool(done), False, info

    def render(self):  # pragma: no cover
        print(
            f"t={self.idx} | price={self.prices[self.idx]:.2f} | "
            f"cash={self.cash:.2f} | shares={self.shares} | pv={self.portfolio_value:.2f}"
        )
