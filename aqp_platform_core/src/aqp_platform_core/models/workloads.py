"""Workload-level wire-format models — actions, run rows, exec, logs.

These types power the extended :class:`InfrastructureProvider` surface
(``exec`` / ``tail_logs`` / ``restart`` / ``rotate_secret``) introduced
by AGENTS rule 45's Management Engine phase. They stay stable across
release cycles since the SPA + Theia desktop + ``rpi_k8s_sdk.aqp``
client all serialise them on the wire.

``WorkloadAction`` + ``WorkloadRun`` + ``WorkloadRunStatus`` are the
shared audit ledger schema used by both the in-process
:class:`aqp_platform_core.runtime.workload.WorkloadRuntime` and the
sidecar :class:`aqp_cp` service. ``aqp_cp.models.audit`` re-exports
them for backwards compatibility.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkloadAction(str, Enum):
    """Set of audited control-plane actions (Management Engine).

    Phase 1 of the control-plane maturation adds ``BUILD_IMAGE``
    (Kaniko in-cluster image builds), ``PROVISION_TENANT`` (per-tenant
    namespace bootstrap), ``HALT`` (kill-switch fan-out), and the
    Terraform IaC actions relocated under the modified rule 42.
    """

    START = "start"
    STOP = "stop"
    SCALE = "scale"
    RESTART = "restart"
    APPLY_CONFIG = "apply_config"
    EXEC = "exec"
    LOGS = "logs"
    DELETE = "delete"
    ROTATE_SECRET = "rotate_secret"
    HALT = "halt"
    # Phase 1 — tenant + build orchestration on the control plane.
    PROVISION_TENANT = "provision_tenant"
    DEPROVISION_TENANT = "deprovision_tenant"
    BUILD_IMAGE = "build_image"
    # Rule-42 relocation — Terraform IaC actions executed by the CP.
    TERRAFORM_PLAN = "terraform_plan"
    TERRAFORM_APPLY = "terraform_apply"
    TERRAFORM_DESTROY = "terraform_destroy"
    TERRAFORM_REFRESH = "terraform_refresh"
    TERRAFORM_IMPORT = "terraform_import"
    TERRAFORM_STATE_PULL = "terraform_state_pull"
    TERRAFORM_VALIDATE = "terraform_validate"
    TERRAFORM_UNLOCK = "terraform_unlock"


class WorkloadRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"
    HALTED = "halted"


class WorkloadRun(BaseModel):
    """Append-only audit row for a single workload operation.

    ``user_id`` is the JWT ``sub``. ``request_id`` is propagated from
    the inbound ``X-Request-Id`` header when present. ``provider`` is
    the active :class:`InfrastructureProvider` alias. ``target`` is the
    resource identifier (service_id, namespace, etc.).

    AGENTS rule 34: every run-producing flow carries ``experiment_id``
    + ``test_id``; the WorkloadRuntime stamps them when set on the
    ``RequestContext``.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique id (UUID4).",
    )
    started_at: datetime
    finished_at: datetime | None = None
    status: WorkloadRunStatus = WorkloadRunStatus.PENDING
    action: WorkloadAction
    provider: str
    target: str
    namespace: str | None = None
    user_id: str
    request_id: str | None = None
    org_id: str | None = None
    workspace_id: str | None = None
    experiment_id: str | None = None
    test_id: str | None = None
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitised request body — secrets MUST be redacted.",
    )
    result: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider response metadata (not raw secrets).",
    )
    error: str | None = None
    halt_reason: str | None = None
    duration_ms: float | None = None


class WorkloadExecResult(BaseModel):
    """Result of an in-pod / in-container command execution.

    Mirrors :class:`aqp.kubernetes.protocol.PodExecResult` but lives in
    ``aqp_platform_core`` so the micro-project and the monolith share
    one Pydantic schema on the wire. ``returncode`` may be ``None`` on
    backends that don't surface an explicit exit code (Docker SDK
    streaming path); callers should inspect ``stderr`` for failure.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    namespace: str | None = None
    container: str | None = None
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    elapsed_ms: float | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkloadLogEvent(BaseModel):
    """Single log frame emitted by :meth:`InfrastructureProvider.tail_logs`.

    The Management Engine adapts these to the canonical
    ``{task_id, stage, message, timestamp, **extras}`` payload shape
    required by AGENTS rule 4 before pushing to the WebSocket bus.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    namespace: str | None = None
    container: str | None = None
    line: str
    timestamp: datetime | None = None
    source: str = Field(
        default="stdout",
        description="'stdout' | 'stderr' | provider-specific stream name.",
    )


class SecretRotationResult(BaseModel):
    """Outcome of a :meth:`InfrastructureProvider.rotate_secret` call.

    Never contains the secret value itself — only metadata about the
    rotation (rotation id, backend, version pointer). The Management
    Engine subagent rule forbids logging secret material, and this
    model is the only sanctioned response shape.
    """

    model_config = ConfigDict(extra="forbid")

    service_id: str
    secret_name: str
    backend: str = Field(
        description=(
            "Secret backend identifier — 'k8s_secret', 'aws_secretsmanager', "
            "'azure_keyvault', 'gcp_secretmanager', 'auth0_management_api', "
            "'cloudflare_zero_trust'."
        )
    )
    rotation_id: str | None = Field(
        default=None,
        description="Provider-issued rotation id when available.",
    )
    new_version: str | None = Field(
        default=None,
        description=(
            "Opaque pointer to the new secret version. Operators / agents "
            "can use this to verify a rotation completed, but MUST NEVER "
            "log it alongside the secret value."
        ),
    )
    rotated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "SecretRotationResult",
    "WorkloadAction",
    "WorkloadExecResult",
    "WorkloadLogEvent",
    "WorkloadRun",
    "WorkloadRunStatus",
]
