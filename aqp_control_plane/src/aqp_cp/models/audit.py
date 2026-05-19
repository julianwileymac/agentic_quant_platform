"""WorkloadRun ledger schema (AGENTS rule 45).

Every mutating control-plane action writes a :class:`WorkloadRun` row
with full audit context BEFORE the provider call executes. The row is
updated with status / error / duration after the call completes.

The ledger backend is pluggable — file-based JSONL is the default;
operators can swap in a Postgres-backed writer by setting
``AQP_CP_AUDIT_BACKEND`` in a future PR. The wire-format model stays
the same.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkloadAction(str, Enum):
    """Set of audited control-plane actions."""

    START = "start"
    STOP = "stop"
    SCALE = "scale"
    RESTART = "restart"
    APPLY_CONFIG = "apply_config"
    EXEC = "exec"
    LOGS = "logs"
    DELETE = "delete"
    ROTATE_SECRET = "rotate_secret"


class WorkloadRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"  # auth failure, scope deny, etc.


class WorkloadRun(BaseModel):
    """Append-only audit row for a single workload operation.

    ``user_id`` is the JWT ``sub``. ``request_id`` is propagated from
    the inbound ``X-Request-Id`` header when present. ``provider`` is
    the active :class:`InfrastructureProvider` alias. ``target`` is the
    resource identifier (service_id, namespace, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(description="Globally unique id (UUID4).")
    started_at: datetime
    finished_at: datetime | None = None
    status: WorkloadRunStatus = WorkloadRunStatus.PENDING
    action: WorkloadAction
    provider: str
    target: str
    user_id: str
    request_id: str | None = None
    org_id: str | None = None
    workspace_id: str | None = None
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitised request body — secrets MUST be redacted.",
    )
    result: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider response metadata (not raw secrets).",
    )
    error: str | None = None
    duration_ms: float | None = None


__all__ = ["WorkloadAction", "WorkloadRun", "WorkloadRunStatus"]
