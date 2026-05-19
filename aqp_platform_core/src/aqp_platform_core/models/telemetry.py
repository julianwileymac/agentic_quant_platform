"""Telemetry wire-format models — metrics + alerts."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class MetricPoint(BaseModel):
    """Single metric observation streamed over the telemetry WebSocket.

    The control-plane telemetry service emits these every 10 s
    (configurable) per registered provider. Consumers reduce by
    ``service_id`` + ``metric`` and render via the existing
    `recharts` widgets in the Vite frontend.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    provider: str
    metric: str = Field(
        description=(
            "Canonical metric name: 'cpu_usage_pct', 'memory_usage_pct', "
            "'memory_used_bytes', 'restart_count', 'replicas_ready', "
            "'replicas_desired'."
        )
    )
    value: float
    unit: str = Field(default="", description="Optional unit string.")
    timestamp: datetime
    labels: dict[str, str] = Field(default_factory=dict)


class MetricSeries(BaseModel):
    """Time-window aggregation of :class:`MetricPoint` for tearsheet rendering."""

    model_config = ConfigDict(extra="forbid")

    service_id: str
    provider: str
    metric: str
    unit: str = ""
    points: list[MetricPoint] = Field(default_factory=list)
    summary: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Optional precomputed stats keyed by name: 'avg', 'p50', "
            "'p95', 'p99', 'min', 'max'."
        ),
    )


class AlertEvent(BaseModel):
    """Compute-starvation or health alert emitted by the telemetry service.

    Forwarded to the aqp_client ``/live/stream`` channel for in-UI
    notifications. Severity thresholds:

    - INFO:     no operator action required.
    - WARNING:  CPU > 75% or memory > 80% for one sample window.
    - CRITICAL: CPU > 85% or memory > 90% (refactor prompt §4.5).
    """

    model_config = ConfigDict(extra="forbid")

    alert_id: str
    service_id: str
    provider: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: datetime
    metrics: list[MetricPoint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AlertEvent",
    "AlertSeverity",
    "MetricPoint",
    "MetricSeries",
]
