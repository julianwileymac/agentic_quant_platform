"""Horizon termination — close the episode at the end of the data window."""
from __future__ import annotations

from typing import Any, ClassVar, Mapping

from aqp_rl.core.termination import BaseTerminationCondition


class HorizonTermination(BaseTerminationCondition):
    """Default termination: ``idx >= horizon - 1``."""

    rl_alias: ClassVar[str] = "HorizonTermination"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "default"

    def check(self, idx: int, horizon: int, env_state: Mapping[str, Any]) -> bool:
        return int(idx) >= int(horizon) - 1


__all__ = ["HorizonTermination"]
