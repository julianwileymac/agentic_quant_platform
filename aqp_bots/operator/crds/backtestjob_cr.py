"""BacktestJob CR — backtest / walk-forward / parameter-sweep."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aqp_bots.operator.crds._common import CrdBase, K8sCondition


class BacktestJobSpecField(BaseModel):
    model_config = ConfigDict(extra="allow")
    botRef: str = ""  # name of a Bot CR (or inline botSpec below)
    botSpec: dict[str, Any] = Field(default_factory=dict)  # for ad-hoc jobs
    kind: Literal[
        "backtest", "walk_forward", "parameter_sweep", "stress", "conformance"
    ] = "backtest"
    startDate: str = ""  # ISO-8601 date
    endDate: str = ""
    initialCash: str = "100000"
    parallelism: int = 1
    parameterGrid: dict[str, Any] = Field(default_factory=dict)
    splits: int = 5  # walk-forward windows
    stressMultiplier: float = 2.0  # for kind=stress
    experimentId: str | None = None
    testId: str | None = None


class BacktestJobStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions: list[K8sCondition] = Field(default_factory=list)
    phase: str = "Pending"  # Pending / Running / Succeeded / Failed
    succeeded: int = 0
    failed: int = 0
    total: int = 0
    mlflowRunId: str | None = None
    resultsRef: dict[str, str] = Field(default_factory=dict)


class BacktestJobCR(CrdBase):
    kind: Literal["BacktestJob"] = "BacktestJob"
    spec: BacktestJobSpecField = Field(default_factory=BacktestJobSpecField)
    status: BacktestJobStatus | None = None


__all__ = ["BacktestJobCR", "BacktestJobSpecField", "BacktestJobStatus"]
