"""Market-making RL environment.

Two registered envs share this module:

- :class:`MarketMakingEnv` — graduated to a *real* Avellaneda-Stoikov
  environment. The agent picks ``(gamma, k_multiplier)`` knobs each
  step; the env evaluates the JAX-compiled
  :func:`aqp.optimal_control.avellaneda_stoikov.compute_optimal_quotes`
  on each tick and computes a stylised PnL under a Cox-process arrival
  model. Same ``rl_alias`` as before so existing configs keep working.
- :class:`MarketMakingStubEnv` — the original stylised env, kept as a
  fallback alias for tests / CI runs that ship without the
  ``optimal-control`` extra.

Inputs to the agent's observation:

- normalised mid-price.
- normalised inventory (signed).
- normalised cash.
- normalised time-to-horizon.
- recent realised volatility.
- recent toxicity score (VPIN proxy).

Action: ``(half_spread_multiplier, inventory_skew_multiplier)`` — both
in [0, 1] and applied to the AvSt closed-form output. The env tracks
``portfolio_value = cash + inventory * mid`` and emits the per-step
delta as the reward (an :class:`aqp_rl.rewards.pnl.PnLTerm`-style
signal). Inventory caps trigger termination via
:class:`aqp_rl.terminations.RiskBreachTermination`.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ENV, RLComponent


class MarketMakingEnv(gym.Env, RLComponent):
    """Avellaneda-Stoikov market-making environment.

    The agent picks two scalar multipliers each step:
    ``half_spread_multiplier`` (scales the AvSt half-spread) and
    ``inventory_skew_multiplier`` (scales the AvSt skew). The
    environment fills the resulting bid/ask quotes against a Cox-
    process Poisson arrival model and returns the per-step PnL.

    The simulator is intentionally lightweight (~1 ms per step) so
    PPO/SAC can train on a million steps in minutes. For full LOB
    realism, prefer :class:`aqp.backtest.hft.LobBacktestEngine` driven
    by a tick-replay dataset.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "MarketMakingEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "market-making"
    rl_tags: ClassVar[tuple[str, ...]] = ("avellaneda_stoikov", "market-making")

    def __init__(
        self,
        *,
        horizon: int = 1000,
        inventory_cap: float = 100.0,
        gamma: float = 0.1,
        sigma: float = 0.01,
        k: float = 1.5,
        arrival_intensity: float = 0.5,
        order_size: float = 1.0,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.inventory_cap = float(inventory_cap)
        self.gamma = float(gamma)
        self.sigma = float(sigma)
        self.k = float(k)
        self.arrival_intensity = float(arrival_intensity)
        self.order_size = float(order_size)

        self.action_space = spaces.Box(low=0.0, high=2.0, shape=(2,), dtype=np.float32)
        # Observation = (mid/100, inventory/cap, cash/1000, t/T, recent_vol, toxicity)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(6,), dtype=np.float32
        )
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.inventory = 0.0
        self.cash = 0.0
        self.mid = 100.0
        self.peak = 0.0
        self.portfolio_value = 0.0
        self.history: list[float] = [0.0]
        self._recent_returns: list[float] = []

    def _obs(self) -> np.ndarray:
        recent_vol = float(np.std(self._recent_returns[-50:])) if self._recent_returns else 0.0
        # Stylised toxicity: scaled |inventory| because the agent gets squeezed
        # in toxic regimes. The real one comes from the analysis flow.
        toxicity = float(min(1.0, abs(self.inventory) / max(self.inventory_cap, 1e-6)))
        return np.asarray(
            [
                self.mid / 100.0,
                self.inventory / max(self.inventory_cap, 1e-6),
                self.cash / 1000.0,
                float(self.step_idx) / max(self.horizon, 1),
                recent_vol * 100.0,
                toxicity,
            ],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {"inventory": self.inventory, "mid": self.mid}

    def step(self, action: np.ndarray):  # type: ignore[override]
        # Lazy import so the env imports cheaply when the optimal-control
        # extra is missing. The fallback is the stylised stub env below.
        try:
            from aqp.optimal_control.avellaneda_stoikov import compute_optimal_quotes
        except Exception:  # noqa: BLE001 — falls back to manual half-spread
            compute_optimal_quotes = None  # type: ignore[assignment]

        spread_mul = float(np.clip(action.flatten()[0], 0.0, 2.0))
        skew_mul = float(np.clip(action.flatten()[1], 0.0, 2.0))

        T_minus_t = max((self.horizon - self.step_idx) / max(self.horizon, 1), 1e-6)

        if compute_optimal_quotes is not None:
            res = compute_optimal_quotes(
                mid_price=self.mid,
                inventory=self.inventory,
                gamma=self.gamma,
                sigma=self.sigma,
                k=self.k,
                T_minus_t=T_minus_t,
            )
            half_spread = res.half_spread * spread_mul
            reservation = res.reservation_price
            # Apply the agent's skew on top of the closed-form reservation.
            skew = (self.inventory / max(self.inventory_cap, 1e-6)) * skew_mul * 0.1
            bid = reservation - half_spread + skew
            ask = reservation + half_spread + skew
        else:
            # Purely-manual fallback for tests without JAX.
            half_spread = 0.5 * spread_mul
            skew = (self.inventory / max(self.inventory_cap, 1e-6)) * skew_mul * 0.1
            bid = self.mid - half_spread + skew
            ask = self.mid + half_spread + skew

        # Cox-process arrivals — fill probabilities decay with spread width.
        bid_fill_p = max(0.0, self.arrival_intensity * np.exp(-self.k * half_spread))
        ask_fill_p = max(0.0, self.arrival_intensity * np.exp(-self.k * half_spread))

        prev_pv = self.portfolio_value
        if self._rng.random() < bid_fill_p and self.inventory < self.inventory_cap:
            self.inventory += self.order_size
            self.cash -= bid * self.order_size
        if self._rng.random() < ask_fill_p and self.inventory > -self.inventory_cap:
            self.inventory -= self.order_size
            self.cash += ask * self.order_size

        # Mid drifts under a stylised GBM.
        drift = self.sigma * float(self._rng.standard_normal())
        self.mid = max(self.mid + drift, 1e-6)
        if self.history:
            ret = (self.mid - 100.0) / 100.0
            self._recent_returns.append(ret)

        self.portfolio_value = self.cash + self.inventory * self.mid
        self.peak = max(self.peak, self.portfolio_value)
        self.history.append(self.portfolio_value)

        reward = self.portfolio_value - prev_pv
        self.step_idx += 1
        terminal = (
            self.step_idx >= self.horizon
            or abs(self.inventory) >= self.inventory_cap
        )
        info: dict[str, Any] = {
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "portfolio_value": self.portfolio_value,
            "peak": self.peak,
            "half_spread": float(half_spread),
            "vega": 0.0,
        }
        return self._obs(), float(reward), bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "portfolio_value": self.portfolio_value,
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "peak": self.peak,
        }


class MarketMakingStubEnv(gym.Env, RLComponent):
    """Original stylised market-making env, preserved for tests / CI.

    Identical surface to the legacy :class:`MarketMakingEnv` shipped
    pre-Avellaneda-Stoikov upgrade. Use this when running CI without
    the ``optimal-control`` extra to keep the registry self-contained.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "MarketMakingStubEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "market-making"
    rl_tags: ClassVar[tuple[str, ...]] = ("placeholder", "market-making", "stub")

    def __init__(self, *, horizon: int = 1000, inventory_cap: float = 100.0) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.inventory_cap = float(inventory_cap)
        self.action_space = spaces.Box(low=0.0, high=1.0, shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32
        )
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.inventory = 0.0
        self.cash = 0.0
        self.mid = 100.0
        self.portfolio_value = 0.0
        self.history = [0.0]

    def _obs(self) -> np.ndarray:
        return np.asarray(
            [self.mid / 100.0, self.inventory / self.inventory_cap, self.cash / 1000.0, float(self.step_idx) / max(self.horizon, 1)],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        half_spread = float(np.clip(action.flatten()[0], 0.0, 1.0)) * 0.5
        skew = float(np.clip(action.flatten()[1], 0.0, 1.0)) - 0.5
        self.mid += float(np.random.normal(scale=0.05))
        bid = self.mid - half_spread + skew * 0.1
        ask = self.mid + half_spread + skew * 0.1
        if np.random.random() < max(0.0, 0.5 - half_spread):
            self.inventory += 1
            self.cash -= bid
        if np.random.random() < max(0.0, 0.5 - half_spread):
            self.inventory -= 1
            self.cash += ask
        self.portfolio_value = self.cash + self.inventory * self.mid
        self.history.append(self.portfolio_value)
        self.step_idx += 1
        terminal = self.step_idx >= self.horizon or abs(self.inventory) >= self.inventory_cap
        reward = self.portfolio_value - (self.history[-2] if len(self.history) > 1 else 0.0)
        info: dict[str, Any] = {
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
            "portfolio_value": self.portfolio_value,
        }
        return self._obs(), float(reward), bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "portfolio_value": self.portfolio_value,
            "inventory": self.inventory,
            "cash": self.cash,
            "mid": self.mid,
        }


__all__ = ["MarketMakingEnv", "MarketMakingStubEnv"]
