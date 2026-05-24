"""``BaseRLEnv`` — composable env that delegates to observation / action /
reward / termination / data-pipeline sub-components.

The existing :class:`StockTradingEnv`, :class:`PortfolioAllocationEnv`,
:class:`StockTradingDiscreteEnv` (and the new FinRL ports) all inherit
from this class so the RL Lab UI can swap any component without
re-writing the env class.

Subclasses must implement at minimum :meth:`_apply_action` (mutates the
internal portfolio state) and :meth:`_collect_env_state` (returns the
current state mapping consumed by observation builders + reward terms).
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, ClassVar, Mapping

import gymnasium as gym
import numpy as np

from aqp_rl.core.action import BaseActionSpace
from aqp_rl.core.base import RL_KIND_ENV, RLComponent
from aqp_rl.core.observation import BaseObservationBuilder
from aqp_rl.core.reward import BaseRewardModel
from aqp_rl.core.termination import BaseTerminationCondition

logger = logging.getLogger(__name__)


class BaseRLEnv(gym.Env, RLComponent):
    """Composable AQP RL environment.

    Holds references to:

    - ``observation_builder`` (:class:`BaseObservationBuilder`) — produces
      the raw obs vector each step.
    - ``action_space_spec`` (:class:`BaseActionSpace`) — declares
      :attr:`gym.Env.action_space` and transforms raw policy outputs.
    - ``reward_model`` (:class:`BaseRewardModel`) — composes the scalar
      reward + per-term decomposition.
    - ``terminations`` (list of :class:`BaseTerminationCondition`) —
      end-of-episode predicates.

    The base class provides the canonical ``reset`` / ``step`` driver;
    subclasses only fill in:

    1. :meth:`_setup_data` — load bars / arrays into ``self`` (called from
       ``__init__``).
    2. :meth:`_apply_action(action)` — mutate the portfolio / cash /
       holdings given a *transformed* action.
    3. :meth:`_collect_env_state()` — return a dict consumed by
       observation builders + reward terms.
    """

    metadata: ClassVar[dict[str, list[str]]] = {"render_modes": ["human"]}

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_ENV

    def __init__(
        self,
        *,
        observation_builder: BaseObservationBuilder | None = None,
        action_space_spec: BaseActionSpace | None = None,
        reward_model: BaseRewardModel | None = None,
        terminations: list[BaseTerminationCondition] | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.observation_builder = observation_builder
        self.action_space_spec = action_space_spec
        self.reward_model = reward_model
        self.terminations = list(terminations or [])
        self._rng = np.random.default_rng(seed)

        self._setup_data()
        self._reset_state()

        # Default obs space: derived from the builder's first sample.
        if action_space_spec is not None:
            self.action_space = action_space_spec.gym_space()
        sample = self._build_obs(0) if observation_builder is not None else None
        if sample is not None:
            self.observation_space = gym.spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=sample.shape,
                dtype=np.float32,
            )

    # ------------------------------------------------------------------ subclass hooks

    def _setup_data(self) -> None:
        """Load bars / arrays into ``self``. Called once during ``__init__``."""
        self.horizon: int = 0
        self.timestamps = []

    @abstractmethod
    def _reset_state(self) -> None:  # pragma: no cover - abstract
        """Reset portfolio / cash / step index for a new episode."""

    @abstractmethod
    def _apply_action(self, action: Any) -> dict[str, Any]:  # pragma: no cover - abstract
        """Mutate state with the (already-transformed) action.

        Returns a dict of side-channel metrics (turnover, cost, drawdown)
        that get folded into the step ``info`` payload and made available
        to the reward model.
        """

    @abstractmethod
    def _collect_env_state(self) -> dict[str, Any]:  # pragma: no cover - abstract
        """Return a flat dict consumed by observation builders + reward terms.

        Convention: include ``cash``, ``portfolio_value``, ``weights`` /
        ``shares``, ``prev_value``, ``peak``, ``timestamp``, plus
        anything the env wants to expose.
        """

    # ------------------------------------------------------------------ helpers

    def _build_obs(self, idx: int) -> np.ndarray:
        if self.observation_builder is None:
            return np.zeros(0, dtype=np.float32)
        return np.asarray(
            self.observation_builder.build(idx, self._collect_env_state()),
            dtype=np.float32,
        )

    def _check_terminations(self, idx: int, env_state: Mapping[str, Any]) -> bool:
        self._last_truncation: tuple[bool, str] = (False, "")
        for cond in self.terminations:
            try:
                if cond.check(idx, self.horizon, env_state):
                    if getattr(cond, "truncates_episode", False):
                        reason = getattr(cond, "truncation_reason", "") or cond.name
                        self._last_truncation = (True, str(reason))
                    return True
            except Exception:
                logger.debug("termination predicate failed: %s", cond, exc_info=True)
        return idx >= self.horizon - 1

    # ------------------------------------------------------------------ Gym API

    def reset(self, *, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._reset_state()
        if self.observation_builder is not None:
            self.observation_builder.reset(self._collect_env_state())
        if self.reward_model is not None:
            self.reward_model.reset()
        for cond in self.terminations:
            cond.reset()
        return self._build_obs(0), {}

    def step(self, action: Any):  # type: ignore[override]
        prev_state = self._collect_env_state()
        if self.action_space_spec is not None:
            action = self.action_space_spec.transform(action)
        side_metrics = self._apply_action(action) or {}
        self.step_idx = getattr(self, "step_idx", 0) + 1
        next_state = self._collect_env_state()

        info: dict[str, Any] = {**side_metrics, "timestamp": next_state.get("timestamp")}
        if self.reward_model is not None:
            reward = float(self.reward_model.compute(prev_state, action, next_state, info))
            info.setdefault(
                "reward_terms",
                self.reward_model.decomposition(prev_state, action, next_state, info),
            )
        else:
            reward = float(next_state.get("portfolio_value", 0.0)) - float(prev_state.get("portfolio_value", 0.0))

        terminated = bool(self._check_terminations(self.step_idx, next_state))
        # Lift truncation metadata recorded by _check_terminations onto
        # the canonical gymnasium (terminated, truncated) split so
        # StopProperlyShaping can find it under ``info['truncated']``
        # and consumers can branch on the truncation reason.
        truncated_flag, truncation_reason = getattr(self, "_last_truncation", (False, ""))
        truncated = bool(truncated_flag)
        if truncated:
            info["truncated"] = True
            info["truncation_reason"] = truncation_reason
        return self._build_obs(self.step_idx), reward, terminated, truncated, info

    def render(self):  # pragma: no cover
        st = self._collect_env_state()
        print(f"t={st.get('step_idx')} | pv={st.get('portfolio_value'):.2f}")


__all__ = ["BaseRLEnv"]
