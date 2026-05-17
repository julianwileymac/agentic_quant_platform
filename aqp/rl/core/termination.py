"""Termination conditions — pluggable end-of-episode predicates.

Each condition gets evaluated at every :meth:`BaseRLEnv.step` and the
env terminates when any returns ``True``. Standard conditions ship in
:mod:`aqp.rl.terminations.*`; researchers compose multiple by setting
``terminations: [...]`` on the env spec.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar, Mapping

from aqp.rl.core.base import RL_KIND_TERMINATION, RLComponent


class BaseTerminationCondition(RLComponent):
    """Abstract termination predicate.

    Truncation semantics
    --------------------

    Subclasses set ``truncates_episode=True`` to mark themselves as a
    hard risk breach (FinRL-X "stop properly" trigger). The env's
    step driver reads this flag and pipes ``info['truncated']`` so
    :class:`StopProperlyShaping` can scale the rewards of truncated
    episodes by a ``coef in [0, 1]`` (NeMo-RL parity).
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_TERMINATION

    truncates_episode: ClassVar[bool] = False
    truncation_reason: ClassVar[str] = ""

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def check(
        self,
        idx: int,
        horizon: int,
        env_state: Mapping[str, Any],
    ) -> bool:
        """Return ``True`` if the episode should terminate at step ``idx``."""

    def reset(self) -> None:
        """Reset any internal state at episode boundary."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "name": self.name,
            "truncates_episode": bool(self.truncates_episode),
            "truncation_reason": str(self.truncation_reason or ""),
        }


__all__ = ["BaseTerminationCondition"]
