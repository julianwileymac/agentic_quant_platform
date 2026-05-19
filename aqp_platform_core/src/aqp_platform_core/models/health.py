"""Health-check wire-format models."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class NodeHealth(BaseModel):
    """Per-node health snapshot.

    Returned by ``GET /manage/cluster/nodes`` (Phase 7 absorption of
    rpi_kubernetes management cluster ops).
    """

    model_config = ConfigDict(extra="forbid")

    node_id: str
    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    role: str = "worker"
    capacity_cpu: str | None = None
    capacity_memory: str | None = None
    allocatable_cpu: str | None = None
    allocatable_memory: str | None = None
    addresses: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    last_seen: datetime | None = None


class ProviderHealth(BaseModel):
    """Health snapshot for a registered :class:`InfrastructureProvider`."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    status: HealthStatus = HealthStatus.UNKNOWN
    available: bool = False
    last_probe_at: datetime | None = None
    latency_ms: float | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["HealthStatus", "NodeHealth", "ProviderHealth"]
