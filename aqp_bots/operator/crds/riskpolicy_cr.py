"""RiskPolicy CR — RTS 6 / SEC 15c3-5 policy.

Both cluster-scoped (``RiskPolicy``) and namespaced
(``NamespacedRiskPolicy``) variants are supported in the operator
ValidatingWebhook; this mirror covers the namespaced version. The
cluster variant is the same shape minus the ``metadata.namespace``.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class HardLimits(BaseModel):
    """Hard blocks — orders ALWAYS rejected when threshold is exceeded.

    Maps onto RTS 6 Art. 15(1)(a)-(d) "hard" controls per
    ESMA Supervisory Briefing §72.
    """

    model_config = ConfigDict(extra="allow")
    priceCollarBps: int | None = None
    maxOrderValueUsd: str | None = None
    maxOrderQty: str | None = None
    maxMessagesPerSecond: int | None = None
    repeatedExecutionThrottleMs: int | None = None


class SoftLimits(BaseModel):
    """Soft blocks — require operator override per ESMA §75/§76."""

    model_config = ConfigDict(extra="allow")
    priceCollarBps: int | None = None
    maxOrderValueUsd: str | None = None
    maxOrderQty: str | None = None
    fatFingerMultiplier: float | None = None


class RiskPolicySpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str = ""
    targets: list[str] = Field(default_factory=list)
    instrumentAllowlist: list[str] = Field(default_factory=list)
    hardLimits: HardLimits = Field(default_factory=HardLimits)
    softLimits: SoftLimits = Field(default_factory=SoftLimits)
    riskServiceEndpoint: str | None = None
    failOpen: bool = False
    citations: list[str] = Field(default_factory=list)


class RiskPolicyStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    botsBound: int = 0
    lastValidatedAt: str | None = None


class RiskPolicyCR(CrdBase):
    kind: Literal["RiskPolicy"] = "RiskPolicy"
    spec: RiskPolicySpecField = Field(default_factory=RiskPolicySpecField)
    status: RiskPolicyStatus | None = None


__all__ = ["HardLimits", "RiskPolicyCR", "RiskPolicySpecField", "RiskPolicyStatus", "SoftLimits"]
