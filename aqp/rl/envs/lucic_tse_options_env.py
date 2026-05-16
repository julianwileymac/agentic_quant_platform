"""Lucic-Tse portfolio options market-making environment.

Wraps the JAX :func:`aqp.options.portfolio_mm.compute_lucic_tse_quotes`
solver in a Gymnasium-compatible env so PPO/SAC can learn to adapt the
``gamma_inv`` (inventory penalty) and ``base_spread`` knobs as a
function of the realised vs implied volatility gap.

Observation
===========

For an option chain of ``n_strikes * n_expiries``, the observation is:

- normalised spot.
- mean realised vs implied vol gap (scalar).
- max absolute inventory across strikes (scalar).
- mean Gamma across the chain (scalar).
- mean Vega across the chain (scalar).
- recent vol-arb PnL (scalar).
- step / horizon ratio (scalar).

Action
======

``(gamma_inv_multiplier, base_spread_multiplier)`` — both in
``[0, 2]``. The agent's job is to widen quotes when toxic and tighten
them when the vol-arb edge is real.

Reward
======

Per-step expected vol-arb PnL minus a quadratic inventory penalty.
"""
from __future__ import annotations

from typing import Any, ClassVar

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from aqp.rl.core.base import RL_KIND_ENV, RLComponent


class LucicTsePortfolioEnv(gym.Env, RLComponent):
    """Lucic-Tse portfolio options MM env."""

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    rl_kind: ClassVar[str] = RL_KIND_ENV
    rl_alias: ClassVar[str] = "LucicTsePortfolioEnv"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "options-market-making"
    rl_tags: ClassVar[tuple[str, ...]] = ("lucic_tse", "options", "vol_arb")

    def __init__(
        self,
        *,
        horizon: int = 500,
        spot: float = 100.0,
        n_strikes: int = 7,
        n_expiries: int = 4,
        gamma_inv: float = 0.05,
        base_spread: float = 0.05,
        hedge_cost: float = 0.001,
        realized_vol: float = 0.20,
        implied_vol: float = 0.22,
        vol_drift_scale: float = 0.005,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.horizon = int(horizon)
        self.spot0 = float(spot)
        self.n_strikes = int(n_strikes)
        self.n_expiries = int(n_expiries)
        self.gamma_inv0 = float(gamma_inv)
        self.base_spread0 = float(base_spread)
        self.hedge_cost = float(hedge_cost)
        self.realized_vol0 = float(realized_vol)
        self.implied_vol0 = float(implied_vol)
        self.vol_drift_scale = float(vol_drift_scale)

        self.action_space = spaces.Box(low=0.0, high=2.0, shape=(2,), dtype=np.float32)
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(7,), dtype=np.float32
        )
        self._rng = np.random.default_rng(seed)
        self._reset_state()

    def _reset_state(self) -> None:
        self.step_idx = 0
        self.spot = self.spot0
        self.realized_vol = self.realized_vol0
        self.implied_vol = self.implied_vol0
        self.inventory = np.zeros(
            (self.n_expiries, self.n_strikes), dtype=np.float64
        )
        self.cumulative_pnl = 0.0

    def _strikes_expiries(self) -> tuple[np.ndarray, np.ndarray]:
        # Strikes ±15% around spot in equal steps.
        offsets = np.linspace(-0.15, 0.15, self.n_strikes)
        strikes = self.spot * (1.0 + offsets)
        # Expiries: weekly to half-year.
        expiries = np.linspace(7.0 / 365.0, 0.5, self.n_expiries)
        return strikes, expiries

    def _greeks(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        from aqp.analysis.pricing import greeks_grid

        strikes, expiries = self._strikes_expiries()
        grid = greeks_grid(
            spot=self.spot,
            strikes=strikes,
            expiries=expiries,
            rate=0.0,
            vol=self.implied_vol,
            option_type="call",
        )
        return grid["price"], grid["gamma"], grid["vega"]

    def _obs(self) -> np.ndarray:
        try:
            _, gamma_surf, vega_surf = self._greeks()
            mean_gamma = float(np.mean(gamma_surf))
            mean_vega = float(np.mean(vega_surf))
        except Exception:  # noqa: BLE001
            mean_gamma = 0.0
            mean_vega = 0.0
        vol_gap = float(self.realized_vol - self.implied_vol)
        max_inv = float(np.max(np.abs(self.inventory))) if self.inventory.size else 0.0
        return np.asarray(
            [
                self.spot / max(self.spot0, 1e-6),
                vol_gap,
                max_inv,
                mean_gamma,
                mean_vega,
                self.cumulative_pnl / 1000.0,
                float(self.step_idx) / max(self.horizon, 1),
            ],
            dtype=np.float32,
        )

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        return self._obs(), {}

    def step(self, action: np.ndarray):  # type: ignore[override]
        try:
            from aqp.options.portfolio_mm import (
                LucicTseParams,
                compute_lucic_tse_quotes,
            )
        except Exception:  # noqa: BLE001
            # Without JAX we can't drive the env; surface a degenerate step.
            self.step_idx += 1
            terminal = self.step_idx >= self.horizon
            return self._obs(), 0.0, terminal, False, {}

        gamma_mul = float(np.clip(action.flatten()[0], 0.0, 2.0))
        spread_mul = float(np.clip(action.flatten()[1], 0.0, 2.0))

        try:
            mid_q, gamma_surf, vega_surf = self._greeks()
            implied_surface = np.full_like(mid_q, fill_value=self.implied_vol)
            params = LucicTseParams(
                gamma_inv=self.gamma_inv0 * gamma_mul,
                base_spread=self.base_spread0 * spread_mul,
                hedge_cost=self.hedge_cost,
            )
            quotes = compute_lucic_tse_quotes(
                spot=self.spot,
                mid_quotes=mid_q,
                gamma_surface=gamma_surf,
                vega_surface=vega_surf,
                realized_vol=self.realized_vol,
                implied_vol=implied_surface,
                inventory=self.inventory,
                params=params,
            )
        except Exception:  # noqa: BLE001
            self.step_idx += 1
            terminal = self.step_idx >= self.horizon
            return self._obs(), 0.0, terminal, False, {}

        # Stylised fills: wider spread → fewer fills.
        spread_surface = quotes.ask - quotes.bid
        fill_prob = np.clip(0.5 - spread_surface * 2.0, 0.0, 1.0)
        # Random sign for each cell — buy ↔ sell flow.
        fill_dir = (self._rng.random(self.inventory.shape) > 0.5).astype(np.float64) * 2.0 - 1.0
        fills = (self._rng.random(self.inventory.shape) < fill_prob).astype(np.float64)
        self.inventory = self.inventory + fills * fill_dir

        # Step PnL = expected vol-arb PnL minus inventory penalty.
        pnl_step = float(np.sum(quotes.expected_pnl))
        inventory_penalty = float(params.gamma_inv * np.sum(self.inventory * self.inventory))
        reward = pnl_step - inventory_penalty
        self.cumulative_pnl += reward

        # Vol drifts: occasionally the realised gap closes.
        self.realized_vol = max(
            0.01,
            self.realized_vol + self.vol_drift_scale * float(self._rng.standard_normal()),
        )
        self.implied_vol = max(
            0.01,
            self.implied_vol + 0.5 * self.vol_drift_scale * float(self._rng.standard_normal()),
        )

        self.step_idx += 1
        terminal = (
            self.step_idx >= self.horizon
            or float(np.max(np.abs(self.inventory))) > 1000.0
        )
        info: dict[str, Any] = {
            "vol_arb_pnl_step": pnl_step,
            "inventory_penalty": inventory_penalty,
            "max_inventory": float(np.max(np.abs(self.inventory))),
            "cumulative_pnl": self.cumulative_pnl,
            "realized_vol": self.realized_vol,
            "implied_vol": self.implied_vol,
            "portfolio_value": float(self.cumulative_pnl),
            "peak": float(self.cumulative_pnl),
        }
        return self._obs(), float(reward), bool(terminal), False, info

    def _collect_env_state(self) -> dict[str, Any]:
        return {
            "step_idx": self.step_idx,
            "spot": self.spot,
            "realized_vol": self.realized_vol,
            "implied_vol": self.implied_vol,
            "max_inventory": float(np.max(np.abs(self.inventory))) if self.inventory.size else 0.0,
            "cumulative_pnl": self.cumulative_pnl,
        }


__all__ = ["LucicTsePortfolioEnv"]
