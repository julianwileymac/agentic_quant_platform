"""KillSwitch CR — three-scope halt."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class KillSwitchSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    scope: Literal["bot", "fleet", "platform"] = "bot"
    target: str = ""  # bot slug / fleet name / "platform"
    mode: Literal["cancel", "flatten", "freeze"] = "cancel"
    reason: str = "manual"
    ttl: str | None = None  # e.g. "1h" — kopf timer auto-releases after this


class KillSwitchStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    engaged: bool = True
    engagedAt: str | None = None
    affectedBots: int = 0


class KillSwitchCR(CrdBase):
    kind: Literal["KillSwitch"] = "KillSwitch"
    spec: KillSwitchSpecField = Field(default_factory=KillSwitchSpecField)
    status: KillSwitchStatus | None = None


__all__ = ["KillSwitchCR", "KillSwitchSpecField", "KillSwitchStatus"]
