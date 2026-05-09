"""Turbulence-based termination."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.termination import BaseTerminationCondition


class TurbulenceTermination(BaseTerminationCondition):
    """End the episode if turbulence exceeds ``max_turbulence``.

    Distinct from :class:`aqp.rl.rewards.gating.TurbulenceGateTerm` —
    that one penalises high turbulence (within the same episode); this
    one terminates the episode entirely (FinRL "stop trading on stress"
    pattern).
    """

    rl_alias: ClassVar[str] = "TurbulenceTermination"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "risk"

    def __init__(self, *, max_turbulence: float = 200.0) -> None:
        super().__init__(name="turbulence_termination")
        self.max_turbulence = float(max_turbulence)

    def check(self, idx: int, horizon: int, env_state: Mapping[str, Any]) -> bool:
        return float(env_state.get("turbulence", 0.0) or 0.0) > self.max_turbulence


__all__ = ["TurbulenceTermination"]
