"""Control-plane Pydantic models.

The deployment / config / telemetry / health wire-format models live in
``aqp_platform_core.models`` and are re-exported here for the API
routers to use without adding two imports. The audit ledger schema
(``WorkloadRun``) is control-plane-specific.
"""
from __future__ import annotations

from aqp_platform_core.models import (
    AlertEvent,
    AlertSeverity,
    ConfigMapPatch,
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
    ErrorEnvelope,
    HealthStatus,
    MetricPoint,
    MetricSeries,
    NodeHealth,
    ProviderHealth,
    ResourceLimits,
    ResponseEnvelope,
    SecretRef,
    ServiceConfig,
)

from aqp_cp.models.audit import (
    WorkloadAction,
    WorkloadRun,
    WorkloadRunStatus,
)

__all__ = [
    # Re-exports
    "AlertEvent",
    "AlertSeverity",
    "ConfigMapPatch",
    "DeploymentLifecyclePhase",
    "DeploymentSpec",
    "DeploymentStatus",
    "ErrorEnvelope",
    "HealthStatus",
    "MetricPoint",
    "MetricSeries",
    "NodeHealth",
    "ProviderHealth",
    "ResourceLimits",
    "ResponseEnvelope",
    "SecretRef",
    "ServiceConfig",
    # Control-plane-specific
    "WorkloadAction",
    "WorkloadRun",
    "WorkloadRunStatus",
]
