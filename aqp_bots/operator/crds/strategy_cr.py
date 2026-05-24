"""Strategy CR — versioned, reusable strategy definition."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class StrategySpecField(BaseModel):
    model_config = ConfigDict(extra="allow")

    moduleClass: str = ""  # aqp.core.registry alias
    modulePath: str = ""   # for build_from_config
    version: str = "1.0.0"
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    references: list[dict[str, Any]] = Field(default_factory=list)
    checksum: str | None = None  # content hash of parameters
    requiredAdapters: list[str] = Field(default_factory=list)


class StrategyStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    botsUsing: int = 0
    lastValidatedAt: str | None = None


class StrategyCR(CrdBase):
    kind: Literal["Strategy"] = "Strategy"
    spec: StrategySpecField = Field(default_factory=StrategySpecField)
    status: StrategyStatus | None = None


__all__ = ["StrategyCR", "StrategySpecField", "StrategyStatus"]
