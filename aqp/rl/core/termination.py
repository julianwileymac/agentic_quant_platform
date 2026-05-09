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

    Subclasses implement :meth:`check` returning ``True`` to end the
    episode. The default ``HorizonTermination`` (``aqp/rl/terminations``
    package) closes when the data window is exhausted.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_TERMINATION

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def check(
        self,
        idx: int,
        horizon: int,
        env_state: Mapping[str, Any],
    ) -> bool:  # pragma: no cover - abstract
        """Return ``True`` if the episode should terminate at step ``idx``."""

    def reset(self) -> None:
        """Reset any internal state at episode boundary."""

    def to_dict(self) -> dict[str, Any]:
        return {"class": type(self).__name__, "name": self.name}


__all__ = ["BaseTerminationCondition"]
