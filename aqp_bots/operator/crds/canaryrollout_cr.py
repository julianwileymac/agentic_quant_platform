"""CanaryRollout CR — Argo Rollouts integration."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class CanaryStep(BaseModel):
    model_config = ConfigDict(extra="allow")
    weight: int | None = None  # 0-100; sets canary traffic weight
    pauseSeconds: int | None = None  # finite pause
    pauseIndefinite: bool = False  # manual promote required
    analysis: list[str] = Field(default_factory=list)  # AnalysisTemplate names


class AnalysisGate(BaseModel):
    model_config = ConfigDict(extra="allow")
    pnlVsStableMinUsd: float = -50.0
    rejectRateMaxPct: float = 1.0
    p99LatencyMaxSeconds: float = 0.001  # 1ms default; HFT can tighten


class CanaryRolloutSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    botRef: str = ""
    canarySpecRef: str = ""  # name of the Bot CR (canary version)
    stableSpecRef: str = ""  # name of the Bot CR (stable version)
    steps: list[CanaryStep] = Field(default_factory=list)
    analysis: AnalysisGate = Field(default_factory=AnalysisGate)
    maxAbortRolloutPnlBleedUsd: float = -500.0  # auto-abort threshold


class CanaryRolloutStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    currentStep: int = 0
    currentWeight: int = 0
    phase: str = "Pending"  # Pending / Progressing / Paused / Healthy / Aborted
    analysisRuns: list[str] = Field(default_factory=list)


class CanaryRolloutCR(CrdBase):
    kind: Literal["CanaryRollout"] = "CanaryRollout"
    spec: CanaryRolloutSpecField = Field(default_factory=CanaryRolloutSpecField)
    status: CanaryRolloutStatus | None = None


__all__ = [
    "AnalysisGate",
    "CanaryRolloutCR",
    "CanaryRolloutSpecField",
    "CanaryRolloutStatus",
    "CanaryStep",
]
