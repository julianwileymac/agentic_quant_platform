"""Margin-call termination."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp.rl.core.termination import BaseTerminationCondition


class MarginCallTermination(BaseTerminationCondition):
    """End the episode if portfolio value falls below an absolute floor.

    Phase 2 of the agentic-RL rollout: marked as a hard risk breach
    (``truncates_episode=True``). The FinRL-X
    :class:`StopProperlyShaping` reward wrapper sees
    ``info['truncated']=True`` and scales the episode reward by
    the configured ``stop_properly_penalty_coef``.
    """

    rl_alias: ClassVar[str] = "MarginCallTermination"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "risk"

    truncates_episode: ClassVar[bool] = True
    truncation_reason: ClassVar[str] = "margin_call"

    def __init__(self, *, floor_value: float = 0.0) -> None:
        super().__init__(name="margin_call_termination")
        self.floor_value = float(floor_value)

    def check(self, idx: int, horizon: int, env_state: Mapping[str, Any]) -> bool:
        pv = float(env_state.get("portfolio_value", 0.0) or 0.0)
        return pv <= self.floor_value


__all__ = ["MarginCallTermination"]
