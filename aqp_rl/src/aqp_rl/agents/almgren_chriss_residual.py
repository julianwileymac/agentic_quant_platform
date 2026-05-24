"""``AlmgrenChrissResidualPolicy`` — RL residual on top of the AC schedule.

Pattern follows Hendricks & Wilcox 2014 ("A Reinforcement Learning
Extension to the Almgren-Chriss Framework for Optimal Trade
Execution"): a learned policy emits a *deviation* from the
deterministic Almgren-Chriss schedule rather than the full action.
The deviation is annealed in over training so the agent starts at
the analytical baseline and drifts toward the learned policy as the
critic gains confidence.

The composite action is::

    n_t = clip(n_t^{AC} + α_t · π_θ(s_t), 0, q_remaining)

Where:

- ``n_t^{AC}`` is the AC schedule's nominal trade for step ``t``.
- ``π_θ`` is the residual RL policy (any :class:`BaseRLAgent`).
- ``α_t`` is the residual-blend coefficient annealed from
  ``alpha_start`` (default 0.0) to ``alpha_end`` (default 1.0) over
  ``alpha_warmup`` env steps.

Inference time: when ``alpha_warmup == 0`` and ``alpha_end == 1.0``
the residual matches the underlying policy exactly. When
``alpha_warmup`` is large the policy stays near the AC schedule
throughout training and only gradually adopts the RL deviation.

Hard rule 16: training/inference go through :class:`RLRuntime`.
Hard rule 38: emitted target action is consumed by the
:class:`aqp_rl.portfolio.pipeline.WeightCentricPipeline` if the env
expects a target weight, otherwise it is the per-step shares-to-trade.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp_rl.analytical.almgren_chriss import (
    AlmgrenChrissParams,
    AlmgrenChrissSchedule,
    build_schedule,
)
from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


class AlmgrenChrissResidualPolicy(BaseRLAgent):
    """RL residual policy anchored on Almgren-Chriss schedule.

    Parameters
    ----------
    base_policy:
        Either an instantiated :class:`BaseRLAgent` or a
        ``{class, module_path, kwargs}`` build-spec resolved via
        :func:`aqp.core.registry.build_from_config`.
    ac_params:
        Either an :class:`AlmgrenChrissParams` instance or a ``dict``
        of kwargs to construct one. Used to materialise the deterministic
        schedule the residual policy modulates.
    alpha_start, alpha_end, alpha_warmup:
        Annealing schedule for the residual-blend coefficient ``α``.
        ``α_t = alpha_start + (alpha_end - alpha_start) · min(t / max(alpha_warmup, 1), 1)``.
        ``alpha_warmup = 0`` collapses to the constant ``alpha_end``.
    clip_to_inventory:
        When ``True`` (default) clamps the composite trade to ``[0,
        q_remaining]`` so a noisy residual cannot overshoot the
        liquidation block.
    """

    rl_alias: ClassVar[str] = "almgren_chriss_residual"
    rl_source: ClassVar[str] = "almgren_chriss_2001"
    rl_category: ClassVar[str] = "execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("residual", "execution", "almgren_chriss")

    algorithm: str = "AlmgrenChrissResidual"

    def __init__(
        self,
        *,
        base_policy: BaseRLAgent | dict[str, Any],
        ac_params: AlmgrenChrissParams | dict[str, Any] | None = None,
        alpha_start: float = 0.0,
        alpha_end: float = 1.0,
        alpha_warmup: int = 0,
        clip_to_inventory: bool = True,
    ) -> None:
        from aqp.core.registry import build_from_config

        if isinstance(base_policy, dict):
            built = build_from_config(base_policy)
            if not isinstance(built, BaseRLAgent):
                raise TypeError(
                    f"AlmgrenChrissResidualPolicy.base_policy must be a BaseRLAgent, "
                    f"got {type(built).__name__}"
                )
            self.base_policy: BaseRLAgent = built
        else:
            self.base_policy = base_policy

        if ac_params is None:
            ac_params = AlmgrenChrissParams()
        elif isinstance(ac_params, dict):
            ac_params = AlmgrenChrissParams(**ac_params)
        self.ac_params: AlmgrenChrissParams = ac_params
        self.schedule: AlmgrenChrissSchedule = build_schedule(self.ac_params)

        if not 0.0 <= alpha_start <= 1.0:
            raise ValueError(f"alpha_start must be in [0, 1]; got {alpha_start!r}")
        if not 0.0 <= alpha_end <= 1.0:
            raise ValueError(f"alpha_end must be in [0, 1]; got {alpha_end!r}")
        if alpha_warmup < 0:
            raise ValueError(f"alpha_warmup must be ≥ 0; got {alpha_warmup!r}")
        self.alpha_start = float(alpha_start)
        self.alpha_end = float(alpha_end)
        self.alpha_warmup = int(alpha_warmup)
        self.clip_to_inventory = bool(clip_to_inventory)

        self._steps_seen = 0
        self._action_dim: int | None = None

    # ------------------------------------------------------------------ lifecycle

    def build(self, env: gym.Env) -> None:
        self.base_policy.build(env)
        try:
            self._action_dim = (
                int(env.action_space.shape[0])
                if env.action_space.shape
                else int(env.action_space.n)
            )
        except Exception:  # noqa: BLE001
            self._action_dim = 1

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
        if env is not None:
            try:
                self._action_dim = (
                    int(env.action_space.shape[0])
                    if env.action_space.shape
                    else int(env.action_space.n)
                )
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ inference

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        out = self.base_policy.predict(obs, deterministic=deterministic)
        if isinstance(out, tuple):
            policy_action, state = out
        else:
            policy_action, state = out, None

        step_idx = self._step_index_from_obs(obs)
        nominal = self._nominal_trade(step_idx)
        alpha = self._alpha_at(self._steps_seen)
        self._steps_seen += 1

        action_arr = np.asarray(policy_action, dtype=np.float32).flatten()
        # Single-asset execution: deviation is a scalar.
        deviation = float(action_arr[0]) if action_arr.size > 0 else 0.0
        composite = nominal + alpha * deviation

        if self.clip_to_inventory:
            q_remaining = self._remaining_inventory(step_idx)
            composite = float(np.clip(composite, 0.0, q_remaining))

        # Reshape back to the policy's action shape so the env sees the
        # same dtype it expects.
        result = np.asarray([composite], dtype=action_arr.dtype if action_arr.size > 0 else np.float32)
        if action_arr.ndim == 0:
            result = result.reshape(())
        return result, state

    # ------------------------------------------------------------------ helpers

    @property
    def model(self) -> Any:
        return self.base_policy.model

    def reset(self) -> None:
        """Reset internal step counter at episode boundary."""
        self._steps_seen = 0

    def _alpha_at(self, t: int) -> float:
        if self.alpha_warmup <= 0:
            return self.alpha_end
        frac = min(t / self.alpha_warmup, 1.0)
        return float(self.alpha_start + (self.alpha_end - self.alpha_start) * frac)

    def _nominal_trade(self, step_idx: int) -> float:
        trades = self.schedule.trades
        if 0 <= step_idx < len(trades):
            return float(trades[step_idx])
        return 0.0

    def _remaining_inventory(self, step_idx: int) -> float:
        positions = self.schedule.positions
        if 0 <= step_idx < len(positions):
            return float(positions[step_idx])
        return float(positions[-1])

    @staticmethod
    def _step_index_from_obs(obs: Any) -> int:
        """Best-effort extraction of the current step index from obs / info.

        Envs that surface ``info['step_idx']`` should pass it through
        their observation builder; absent that we fall back to ``0``
        (the caller probably has a separate mechanism to drive the AC
        schedule).
        """
        if isinstance(obs, dict) and "step_idx" in obs:
            try:
                return int(obs["step_idx"])
            except (TypeError, ValueError):
                return 0
        return 0


__all__ = ["AlmgrenChrissResidualPolicy"]
