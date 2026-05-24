"""``AvellanedaStoikovResidualPolicy`` — RL residual on top of AS quotes.

Pattern mirrors :class:`aqp_rl.agents.almgren_chriss_residual.AlmgrenChrissResidualPolicy`
for market-making: the analytical Avellaneda-Stoikov reservation
price + half-spread is the anchor, and a learned RL policy emits a
``(Δ_bid_depth, Δ_ask_depth)`` deviation. The deviation is annealed
in via the same ``alpha`` schedule.

The composite output is the env-facing
``(half_spread_multiplier, inventory_skew_multiplier)`` pair (matching
:class:`aqp_rl.envs.MarketMakingEnv`'s action contract)::

    spread_mul = 1.0 + α · Δ_spread
    skew_mul   = 1.0 + α · Δ_skew

The base AS quote is computed lazily by the env (which has the live
mid-price + inventory + time-to-horizon). The residual policy just
modulates the multipliers — the AS math itself lives in
:mod:`aqp.optimal_control.avellaneda_stoikov` and is reused.

Hard rule 16: training/inference through :class:`RLRuntime`.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


class AvellanedaStoikovResidualPolicy(BaseRLAgent):
    """RL residual policy on top of Avellaneda-Stoikov quote multipliers.

    Parameters
    ----------
    base_policy:
        Underlying :class:`BaseRLAgent` (or build-spec dict).
    alpha_start, alpha_end, alpha_warmup:
        Annealing schedule for the deviation multiplier.
    clip_low, clip_high:
        Range the composite multipliers are clipped to. Matches the
        :class:`MarketMakingEnv` action-space bounds
        (``Box(0, 2, shape=(2,))``).
    """

    rl_alias: ClassVar[str] = "avellaneda_stoikov_residual"
    rl_source: ClassVar[str] = "avellaneda_stoikov_2008"
    rl_category: ClassVar[str] = "market_making"
    rl_tags: ClassVar[tuple[str, ...]] = ("residual", "market_making", "avellaneda_stoikov")

    algorithm: str = "AvellanedaStoikovResidual"

    def __init__(
        self,
        *,
        base_policy: BaseRLAgent | dict[str, Any],
        alpha_start: float = 0.0,
        alpha_end: float = 1.0,
        alpha_warmup: int = 0,
        clip_low: float = 0.0,
        clip_high: float = 2.0,
    ) -> None:
        from aqp.core.registry import build_from_config

        if isinstance(base_policy, dict):
            built = build_from_config(base_policy)
            if not isinstance(built, BaseRLAgent):
                raise TypeError(
                    f"AvellanedaStoikovResidualPolicy.base_policy must be a BaseRLAgent, "
                    f"got {type(built).__name__}"
                )
            self.base_policy: BaseRLAgent = built
        else:
            self.base_policy = base_policy

        if not 0.0 <= alpha_start <= 1.0:
            raise ValueError(f"alpha_start must be in [0, 1]; got {alpha_start!r}")
        if not 0.0 <= alpha_end <= 1.0:
            raise ValueError(f"alpha_end must be in [0, 1]; got {alpha_end!r}")
        if alpha_warmup < 0:
            raise ValueError(f"alpha_warmup must be ≥ 0; got {alpha_warmup!r}")
        if clip_low >= clip_high:
            raise ValueError(
                f"clip_low must be < clip_high; got ({clip_low}, {clip_high})"
            )

        self.alpha_start = float(alpha_start)
        self.alpha_end = float(alpha_end)
        self.alpha_warmup = int(alpha_warmup)
        self.clip_low = float(clip_low)
        self.clip_high = float(clip_high)

        self._steps_seen = 0

    # ------------------------------------------------------------------ lifecycle

    def build(self, env: gym.Env) -> None:
        self.base_policy.build(env)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        self.base_policy.train(
            total_timesteps=total_timesteps,
            callbacks=callbacks,
            log_interval=log_interval,
        )

    def save(self, path: str | Path) -> Path:
        return self.base_policy.save(path)

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        self.base_policy.load(path, env=env)

    # ------------------------------------------------------------------ inference

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        out = self.base_policy.predict(obs, deterministic=deterministic)
        if isinstance(out, tuple):
            policy_action, state = out
        else:
            policy_action, state = out, None

        alpha = self._alpha_at(self._steps_seen)
        self._steps_seen += 1

        action_arr = np.asarray(policy_action, dtype=np.float32).flatten()
        # The policy emits a 2-vector deviation (spread, skew). We
        # interpret the policy's raw output as the *deviation around
        # 1.0* so the AS baseline corresponds to deviation = 0.
        # Truncate or pad the policy emission to length 2 — short
        # emissions are pad-with-zero (no skew adjustment), long
        # emissions are truncated to the canonical (spread, skew)
        # axis order.
        if action_arr.size >= 2:
            deviation = action_arr[:2]
        else:
            deviation = np.concatenate(
                [action_arr, np.zeros(2 - action_arr.size, dtype=np.float32)]
            )

        composite = 1.0 + alpha * deviation
        composite = np.clip(composite, self.clip_low, self.clip_high).astype(np.float32)
        return composite, state

    # ------------------------------------------------------------------ helpers

    @property
    def model(self) -> Any:
        return self.base_policy.model

    def reset(self) -> None:
        self._steps_seen = 0

    def _alpha_at(self, t: int) -> float:
        if self.alpha_warmup <= 0:
            return self.alpha_end
        frac = min(t / self.alpha_warmup, 1.0)
        return float(self.alpha_start + (self.alpha_end - self.alpha_start) * frac)


__all__ = ["AvellanedaStoikovResidualPolicy"]
