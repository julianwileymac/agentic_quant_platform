"""``BaseAdvantageEstimator`` — abstract contract for advantage estimators.

In policy-gradient methods the advantage function measures how much
better a specific action performed relative to the expected baseline
behaviour of the current policy. AQP factors this out of the policy
optimiser so the same estimator can be used by any RL adapter
(SB3, CleanRL, ElegantRL, NeMo-RL via the optional Phase 9 adapter).

Concrete estimators register via the :class:`RLComponentMeta`
metaclass with ``rl_kind="rl_advantage_estimator"``; the RL Lab UI
palette and ``GET /rl/components/rl_advantage_estimator`` enumerate
them automatically.

Reward signature
----------------

All estimators consume a batch of (rewards, values, dones,
truncated, group_ids) tensors and return an
:class:`AdvantageOutput`. The ``group_ids`` tensor identifies which
parallel rollout cohort each transition belongs to — required by
:class:`ReinforcePlusPlusAdvantage` and :class:`GRPOAdvantage`.
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np

from aqp.rl.core.base import RL_KIND_ADVANTAGE, RLComponent

logger = logging.getLogger(__name__)


@dataclass
class AdvantageOutput:
    """Bundle returned by :meth:`BaseAdvantageEstimator.compute`.

    Attributes
    ----------
    advantages:
        Per-transition advantage values, normalised when
        :attr:`global_normalization` is ``True``.
    returns:
        Per-transition discounted returns (``advantage + value`` for
        GAE; cumulative reward-to-go for REINFORCE / GRPO).
    baselines:
        Per-transition baseline used for advantage subtraction. Useful
        for diagnostics + logging.
    std:
        Per-transition standard deviation used for normalisation.
        ``None`` when the estimator does not normalise.
    extras:
        Free-form dict for estimator-specific telemetry (e.g.
        cohort-level mean reward for GRPO, truncation count for
        REINFORCE++).
    """

    advantages: np.ndarray
    returns: np.ndarray
    baselines: np.ndarray | None = None
    std: np.ndarray | None = None
    extras: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "advantages": np.asarray(self.advantages, dtype=np.float64).tolist(),
            "returns": np.asarray(self.returns, dtype=np.float64).tolist(),
            "baselines": (
                np.asarray(self.baselines, dtype=np.float64).tolist()
                if self.baselines is not None
                else None
            ),
            "std": (
                np.asarray(self.std, dtype=np.float64).tolist()
                if self.std is not None
                else None
            ),
            "extras": dict(self.extras or {}),
        }


class BaseAdvantageEstimator(RLComponent):
    """Abstract advantage estimator.

    Subclasses implement :meth:`compute` returning an
    :class:`AdvantageOutput`. The estimator is *pure* — no
    cross-batch state. Stateful diagnostics (running cost stats,
    moving averages) belong in callbacks / observability code.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_ADVANTAGE

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def compute(
        self,
        *,
        rewards: np.ndarray,
        values: np.ndarray | None = None,
        dones: np.ndarray | None = None,
        truncated: np.ndarray | None = None,
        group_ids: np.ndarray | None = None,
        valid_mask: np.ndarray | None = None,
    ) -> AdvantageOutput:  # pragma: no cover - abstract
        """Compute advantages + returns for a batch of transitions.

        Parameters
        ----------
        rewards:
            Shape ``(batch_size,)`` per-transition shaped reward
            (after :class:`StopProperlyShaping` and the rest of the
            reward pipeline). REQUIRED.
        values:
            Shape ``(batch_size,)`` value function predictions for the
            same transitions. Required by GAE; ignored by REINFORCE++
            / GRPO.
        dones:
            Bool tensor marking natural-termination boundaries
            (horizon hit). Used to clamp the value bootstrap.
        truncated:
            Bool tensor marking risk-overlay / risk-termination
            boundaries (the FinRL-X "stop properly" trigger). The
            advantage estimator does NOT itself apply the
            ``stop_properly`` penalty — that happens upstream in
            :class:`StopProperlyShaping`. The flag is plumbed
            through for diagnostics + ``AdvantageOutput.extras``.
        group_ids:
            Cohort identifiers for the leave-one-out / group-relative
            estimators. Same length as ``rewards``; entries with the
            same id share a baseline.
        valid_mask:
            Optional bool mask of valid transitions (matches the
            NeMo-RL ``valid_mask`` argument).
        """

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "name": self.name}


__all__ = [
    "AdvantageOutput",
    "BaseAdvantageEstimator",
]
