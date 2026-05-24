"""Bot CR — the atomic deployable unit.

Schema follows blueprint §K.1. Spec mirrors :class:`BotSpec` from
:mod:`aqp_bots.spec` so the operator can deserialize the CR's
``.spec`` straight into a :class:`BotSpec` and snapshot it via
``persist_spec()``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class StrategyRef(BaseModel):
    name: str
    version: str | None = None


class CapabilitiesField(BaseModel):
    model_config = ConfigDict(extra="allow")
    frequency: Literal["hft", "mid", "low", "eod", "event"] = "mid"
    assetClasses: list[str] = Field(default_factory=list)
    venues: list[str] = Field(default_factory=list)
    needsGpu: bool = False
    needsNumaPinning: bool = False
    needsHugepagesMiB: int = 0
    needsSrIov: bool = False
    expectedP99TickToTradeUs: int | None = None
    maxCapitalUsd: str = "0"


class ResourcesField(BaseModel):
    model_config = ConfigDict(extra="allow")
    requests: dict[str, str] = Field(default_factory=dict)
    limits: dict[str, str] = Field(default_factory=dict)


class SchedulingHints(BaseModel):
    model_config = ConfigDict(extra="allow")
    nodeSelector: dict[str, str] = Field(default_factory=dict)
    tolerations: list[dict[str, Any]] = Field(default_factory=list)
    affinity: dict[str, Any] = Field(default_factory=dict)


class BotSpecField(BaseModel):
    """The ``.spec`` of a Bot CR."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    strategyRef: StrategyRef | None = None
    fleet: str | None = None
    capabilities: CapabilitiesField = Field(default_factory=CapabilitiesField)
    riskPolicyRefs: list[str] = Field(default_factory=list)
    marketDataRefs: list[str] = Field(default_factory=list)
    executionVenueRefs: list[str] = Field(default_factory=list)
    resources: ResourcesField = Field(default_factory=ResourcesField)
    schedulingHints: SchedulingHints = Field(default_factory=SchedulingHints)
    # Embed the full :class:`BotSpec` payload here so the operator can
    # rebuild the legacy spec without a second API round-trip. The
    # validator merges the CR-level fields above into the embedded
    # spec at reconcile time.
    botSpec: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class BotStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    phase: str = "Pending"  # Pending / Running / Paused / Draining / Stopped / Killed / Failed
    conditions: list[K8sCondition] = Field(default_factory=list)
    observedGeneration: int | None = None
    pnlUsd: str | None = None
    lastReconciledAt: datetime | None = None
    workloadType: str | None = None  # Deployment / StatefulSet / DaemonSet / CronJob / Job
    workloadName: str | None = None
    specVersion: str | None = None
    killSwitchEngaged: bool = False
    killSwitchReason: str | None = None


class BotCR(CrdBase):
    """``quantbot.io/v1 Bot``."""

    kind: Literal["Bot"] = "Bot"
    spec: BotSpecField = Field(default_factory=BotSpecField)
    status: BotStatus | None = None


__all__ = [
    "BotCR",
    "BotSpecField",
    "BotStatus",
    "CapabilitiesField",
    "ResourcesField",
    "SchedulingHints",
    "StrategyRef",
]
