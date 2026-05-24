"""BotFleet CR — logical group of bots with shared policy."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class BotFleetSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str = ""
    botSelector: dict[str, str] = Field(default_factory=dict)
    sharedRiskPolicyRefs: list[str] = Field(default_factory=list)
    maxCapitalUsd: str | None = None
    maxBotCount: int | None = None
    halt: bool = False  # set by KillSwitch reconciler


class BotFleetStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    botCount: int = 0
    runningBotCount: int = 0
    haltedBotCount: int = 0


class BotFleetCR(CrdBase):
    kind: Literal["BotFleet"] = "BotFleet"
    spec: BotFleetSpecField = Field(default_factory=BotFleetSpecField)
    status: BotFleetStatus | None = None


__all__ = ["BotFleetCR", "BotFleetSpecField", "BotFleetStatus"]
