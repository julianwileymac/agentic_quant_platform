"""Wire-format Pydantic models used by both planes.

These are the request / response shapes flowing across the control
plane API and the in-AQP ``/control-plane/*`` proxy. Adding fields is
fine; renaming or removing them is a major-version bump.
"""
from __future__ import annotations

from aqp_platform_core.models.config import (
    ConfigMapPatch,
    SecretRef,
    ServiceConfig,
)
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
    ResourceLimits,
)
from aqp_platform_core.models.envelope import ErrorEnvelope, ResponseEnvelope
from aqp_platform_core.models.health import (
    HealthStatus,
    NodeHealth,
    ProviderHealth,
)
from aqp_platform_core.models.telemetry import (
    AlertEvent,
    AlertSeverity,
    MetricPoint,
    MetricSeries,
)
from aqp_platform_core.models.tenancy import (
    NetworkPolicyMode,
    TenantLimitRange,
    TenantNamespacePhase,
    TenantNamespaceSpec,
    TenantNamespaceStatus,
    TenantPlan,
    TenantQuotas,
)
from aqp_platform_core.models.terraform import (
    TerraformRunKind,
    TerraformRunResult,
    TerraformRunStatus,
    TerraformStackSpec,
    TerraformStateBackend,
)
from aqp_platform_core.models.workloads import (
    SecretRotationResult,
    WorkloadAction,
    WorkloadExecResult,
    WorkloadLogEvent,
    WorkloadRun,
    WorkloadRunStatus,
)

__all__ = [
    # config
    "ConfigMapPatch",
    "SecretRef",
    "ServiceConfig",
    # deployment
    "DeploymentLifecyclePhase",
    "DeploymentSpec",
    "DeploymentStatus",
    "ResourceLimits",
    # envelope
    "ErrorEnvelope",
    "ResponseEnvelope",
    # health
    "HealthStatus",
    "NodeHealth",
    "ProviderHealth",
    # telemetry
    "AlertEvent",
    "AlertSeverity",
    "MetricPoint",
    "MetricSeries",
    # tenancy
    "NetworkPolicyMode",
    "TenantLimitRange",
    "TenantNamespacePhase",
    "TenantNamespaceSpec",
    "TenantNamespaceStatus",
    "TenantPlan",
    "TenantQuotas",
    # terraform (rule-42 relocation)
    "TerraformRunKind",
    "TerraformRunResult",
    "TerraformRunStatus",
    "TerraformStackSpec",
    "TerraformStateBackend",
    # workloads (Management Engine — actions, runs, exec, logs, secrets)
    "SecretRotationResult",
    "WorkloadAction",
    "WorkloadExecResult",
    "WorkloadLogEvent",
    "WorkloadRun",
    "WorkloadRunStatus",
]
