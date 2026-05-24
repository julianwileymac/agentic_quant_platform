"""ExecutionVenue CR — venue execution + drop-copy config."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition
from aqp_bots.operator.crds.marketdatafeed_cr import SecretRef


class DropCopyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    endpoint: str = ""
    sessionId: str = ""
    credentialsRef: SecretRef | None = None


class ExecutionVenueSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    venue: str = ""
    transport: Literal["fix", "rest", "grpc", "onchain", "bridge"] = "fix"
    adapter: str = ""
    endpoint: str = ""
    credentialsRef: SecretRef | None = None
    supportedOrderTypes: list[str] = Field(default_factory=lambda: ["market", "limit"])
    maxOrdersPerSecond: int | None = None
    dropCopy: DropCopyConfig = Field(default_factory=DropCopyConfig)
    extras: dict[str, Any] = Field(default_factory=dict)


class ExecutionVenueStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    connected: bool = False
    lastReconcileAt: str | None = None


class ExecutionVenueCR(CrdBase):
    kind: Literal["ExecutionVenue"] = "ExecutionVenue"
    spec: ExecutionVenueSpecField = Field(default_factory=ExecutionVenueSpecField)
    status: ExecutionVenueStatus | None = None


__all__ = [
    "DropCopyConfig",
    "ExecutionVenueCR",
    "ExecutionVenueSpecField",
    "ExecutionVenueStatus",
]
