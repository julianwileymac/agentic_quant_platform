"""Deployment lifecycle wire-format models.

The :class:`DeploymentSpec` is the input every
:class:`aqp_platform_core.providers.InfrastructureProvider` translates
to its backend's native API. The :class:`DeploymentStatus` is the
normalised output every provider returns.

These types must stay stable across release cycles since both planes
and the ``rpi_k8s_sdk.aqp`` client serialise them on the wire.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class DeploymentLifecyclePhase(str, Enum):
    """Normalised lifecycle phases across all provider backends."""

    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    UPDATING = "updating"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ResourceLimits(BaseModel):
    """Per-container resource requests + limits.

    All values are strings to preserve K8s-style units (``"500m"``,
    ``"2Gi"``). Providers parse them according to their target's
    convention.
    """

    model_config = ConfigDict(extra="forbid")

    cpu_request: str | None = Field(
        default=None,
        description="CPU request, e.g. '250m' or '1'.",
    )
    cpu_limit: str | None = Field(
        default=None,
        description="CPU limit, e.g. '500m' or '2'.",
    )
    memory_request: str | None = Field(
        default=None,
        description="Memory request, e.g. '512Mi' or '1Gi'.",
    )
    memory_limit: str | None = Field(
        default=None,
        description="Memory limit, e.g. '1Gi' or '4Gi'.",
    )
    ephemeral_storage_request: str | None = Field(
        default=None,
        description="Ephemeral storage request, e.g. '1Gi'.",
    )
    ephemeral_storage_limit: str | None = Field(
        default=None,
        description="Ephemeral storage limit, e.g. '4Gi'.",
    )


class DeploymentSpec(BaseModel):
    """Provider-agnostic deployment specification.

    Maps to a Kubernetes Deployment, a Docker Compose service, an ECS
    task definition, an ACI container group, or a Cloud Run revision
    depending on the active :class:`InfrastructureProvider`.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str = Field(
        description=(
            "Logical service identifier. Maps to a Compose service "
            "name, K8s Deployment name, ECS service name, ACI container "
            "group name, or Cloud Run service name."
        )
    )
    image: str = Field(
        description=(
            "Fully-qualified container image including tag, e.g. "
            "'ghcr.io/julianwiley/aqp-api:2026-05-18-sha'."
        )
    )
    replicas: PositiveInt = Field(
        default=1,
        description=(
            "Desired replica count. For ACI / Cloud Run this is "
            "translated to the closest equivalent (min-instances)."
        ),
    )
    namespace: str = Field(
        default="default",
        description=(
            "Logical namespace. Kubernetes namespace name, Compose "
            "project name, ECS cluster name, ACI resource group name, "
            "or Cloud Run region."
        ),
    )
    command: list[str] | None = Field(
        default=None,
        description="Override the image's default ENTRYPOINT.",
    )
    args: list[str] | None = Field(
        default=None,
        description="Override the image's default CMD.",
    )
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Plain environment variables. Secrets go in env_from_secrets.",
    )
    env_from_secrets: list[str] = Field(
        default_factory=list,
        description=(
            "Names of secret references the provider must inject as "
            "env vars (K8s envFrom secretRef, ACI secure env, AWS SSM "
            "SecureString, GCP Secret Manager secret)."
        ),
    )
    ports: list[int] = Field(
        default_factory=list,
        description="Container ports to expose.",
    )
    resources: ResourceLimits = Field(
        default_factory=ResourceLimits,
        description="Resource requests + limits.",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Provider-portable labels. Reproduced as K8s labels, "
            "Compose container labels, AWS tags, Azure resource tags, "
            "and GCP labels."
        ),
    )
    health_check_path: str | None = Field(
        default=None,
        description="HTTP path for readiness / liveness probes.",
    )
    health_check_port: int | None = Field(
        default=None,
        description=(
            "Port for HTTP health checks. Defaults to ports[0] when "
            "unset."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific extras (e.g. ACI subnet, ECS task role).",
    )


class DeploymentStatus(BaseModel):
    """Normalised status returned by every provider.

    Augmented with a ``provider`` field so the operator knows which
    backend produced the snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    provider: str = Field(
        description=(
            "Provider key — one of 'docker_compose', 'kubernetes', "
            "'aws', 'azure', 'gcp'."
        )
    )
    phase: DeploymentLifecyclePhase = DeploymentLifecyclePhase.UNKNOWN
    replicas_desired: int = 0
    replicas_ready: int = 0
    image: str | None = None
    namespace: str | None = None
    last_transition_at: datetime | None = None
    conditions: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Provider-native condition records (e.g. K8s pod "
            "conditions, ECS deployment events)."
        ),
    )
    endpoints: dict[str, str] = Field(
        default_factory=dict,
        description="Resolved external URLs keyed by purpose.",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw provider response for debugging.",
    )


__all__ = [
    "DeploymentLifecyclePhase",
    "DeploymentSpec",
    "DeploymentStatus",
    "ResourceLimits",
]
