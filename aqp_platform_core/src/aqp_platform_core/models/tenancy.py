"""Tenancy value types — :class:`TenantNamespaceSpec` + :class:`TenantNamespaceStatus`.

Used by :meth:`aqp_platform_core.providers.InfrastructureProvider.provision_tenant_namespace`
and the matching ``/manage/tenants/*`` admin surface. The Kubernetes
provider renders these into Namespace + ResourceQuota + LimitRange +
NetworkPolicy + PSA-label manifests; other providers (compose, AWS,
Azure, GCP, Cloudflare) raise :class:`InfrastructureProviderUnavailable`
until they ship their own translators.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TenantPlan(str, Enum):
    """Commercial plan for a tenant — drives default quotas + policies."""

    B2B = "b2b"
    B2C = "b2c"
    INTERNAL = "internal"
    SANDBOX = "sandbox"


class NetworkPolicyMode(str, Enum):
    """How aggressively to lock down cross-namespace traffic."""

    OPEN = "open"  # no NetworkPolicy applied (legacy compatibility)
    INTRA_TENANT = "intra_tenant"  # default-deny + intra-tenant allow
    STRICT = "strict"  # default-deny only (explicit egress / ingress required)


class TenantQuotas(BaseModel):
    """Resource quotas for a tenant namespace.

    Defaults mirror the blueprint's B2B baseline. Override per-plan
    or per-customer via the admin tenant-vending wizard.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cpu: str = Field(default="8", description="ResourceQuota requests.cpu")
    memory: str = Field(default="16Gi", description="ResourceQuota requests.memory")
    gpus: int = Field(default=0, ge=0, description="ResourceQuota requests.nvidia.com/gpu")
    pvcs: int = Field(default=10, ge=0, description="ResourceQuota persistentvolumeclaims")
    pods: int = Field(default=50, ge=0, description="ResourceQuota count/pods")
    services: int = Field(default=20, ge=0, description="ResourceQuota count/services")
    secrets: int = Field(default=50, ge=0, description="ResourceQuota count/secrets")
    configmaps: int = Field(default=50, ge=0, description="ResourceQuota count/configmaps")


class TenantLimitRange(BaseModel):
    """Per-container LimitRange defaults applied to every Pod.

    Conservative defaults so a workload without explicit requests
    doesn't blow the namespace quota.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_cpu: str = Field(default="500m")
    default_memory: str = Field(default="512Mi")
    default_request_cpu: str = Field(default="100m")
    default_request_memory: str = Field(default="128Mi")
    max_cpu: str = Field(default="4")
    max_memory: str = Field(default="8Gi")


class TenantNamespaceSpec(BaseModel):
    """Inputs to :meth:`InfrastructureProvider.provision_tenant_namespace`.

    The provider returns a :class:`TenantNamespaceStatus` describing
    the result of the SSA (server-side-apply) round-trip.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., min_length=1, max_length=63, pattern=r"^[a-z0-9-]+$")
    plan: TenantPlan = TenantPlan.B2B
    namespace_prefix: str = Field(
        default="tenant",
        description="Namespace becomes '{prefix}-{tenant_id}'.",
        min_length=1,
        max_length=20,
        pattern=r"^[a-z0-9-]+$",
    )
    quotas: TenantQuotas = Field(default_factory=TenantQuotas)
    limit_range: TenantLimitRange = Field(default_factory=TenantLimitRange)
    network_policy_mode: NetworkPolicyMode = NetworkPolicyMode.INTRA_TENANT
    psa_enforce: str = Field(default="restricted", pattern=r"^(restricted|baseline|privileged)$")
    psa_audit: str = Field(default="restricted", pattern=r"^(restricted|baseline|privileged)$")
    psa_warn: str = Field(default="restricted", pattern=r"^(restricted|baseline|privileged)$")
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)

    def namespace(self) -> str:
        return f"{self.namespace_prefix}-{self.tenant_id}"


class TenantNamespacePhase(str, Enum):
    """Lifecycle phase of a tenant namespace SSA round-trip."""

    PENDING = "pending"
    APPLIED = "applied"
    DEGRADED = "degraded"
    FAILED = "failed"


class TenantNamespaceStatus(BaseModel):
    """Result of :meth:`InfrastructureProvider.provision_tenant_namespace`.

    Conditions follow the Kubernetes API-conventions shape (``type``,
    ``status``, ``reason``, ``message``) so the admin UI can render
    them with the same component used for ``DeploymentStatus``.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    namespace: str
    provider: str
    phase: TenantNamespacePhase = TenantNamespacePhase.PENDING
    applied_at: datetime | None = None
    objects_applied: list[str] = Field(
        default_factory=list,
        description="Kind/Name of each Kubernetes object SSA'd in this call.",
    )
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None


__all__ = [
    "NetworkPolicyMode",
    "TenantLimitRange",
    "TenantNamespacePhase",
    "TenantNamespaceSpec",
    "TenantNamespaceStatus",
    "TenantPlan",
    "TenantQuotas",
]
