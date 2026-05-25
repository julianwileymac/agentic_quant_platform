"""Terraform value types — shared between ``aqp_control_plane`` and ``aqp/``.

After the modified rule 42, ``aqp_control_plane`` owns the actual
:class:`TerraformRuntime` implementation. The monolith brokers via
HTTP; both planes need the same wire-format value types, so they live
here in ``aqp_platform_core``.

The hash-locked snapshot pattern from rule 43 stays — every distinct
:class:`TerraformStackSpec` content produces a new
``terraform_stack_spec_versions`` row in the monolith's Postgres
ledger. The CP computes the SHA-256 deterministically and the
monolith's :class:`HttpAuditSink` consumer dedupes on it.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TerraformRunKind(str, Enum):
    PLAN = "plan"
    APPLY = "apply"
    DESTROY = "destroy"
    REFRESH = "refresh"
    IMPORT = "import"
    STATE_PULL = "state_pull"
    VALIDATE = "validate"
    UNLOCK = "unlock"


class TerraformRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    HALTED = "halted"
    REJECTED = "rejected"


class TerraformStateBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"
    AZURERM = "azurerm"
    GCS = "gcs"
    HCP = "hcp"


class TerraformStackSpec(BaseModel):
    """Hash-locked spec describing one Terraform stack.

    The ``stack_name`` is the human-readable handle; ``workspace_id``
    is the runtime instance (a stack may have many workspaces — dev,
    staging, prod). The ``hcl_modules`` map is the bundle of rendered
    Jinja templates that compose the stack.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    stack_name: str = Field(..., min_length=1, max_length=128)
    workspace_id: str = Field(..., min_length=1, max_length=128)
    state_backend: TerraformStateBackend = TerraformStateBackend.LOCAL
    state_backend_config: dict[str, str] = Field(default_factory=dict)
    hcl_modules: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of relative-path -> rendered HCL contents. The runner "
            "writes these to the workspace dir before invoking terraform."
        ),
    )
    variables: dict[str, Any] = Field(default_factory=dict)
    providers_lock: str = Field(
        default="",
        description="Verbatim contents of .terraform.lock.hcl (when pinned).",
    )

    def compute_hash(self) -> str:
        body = self.model_dump(mode="json")
        # Stable ordering so the SHA matches whatever the monolith
        # observed previously for the same content.
        blob = json.dumps(body, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


class TerraformRunResult(BaseModel):
    """Outcome of a single :class:`TerraformRuntime.execute` call."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    run_kind: TerraformRunKind
    status: TerraformRunStatus
    stack_name: str
    workspace_id: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_ms: float | None = None
    plan_summary: dict[str, Any] = Field(default_factory=dict)
    log_excerpt: str = Field(
        default="",
        description="Last N lines of the runner stdout/stderr (redacted).",
    )
    artifact_uri: str = Field(
        default="",
        description="Optional pointer to the persisted plan JSON / state snapshot.",
    )
    error: str | None = None
    halt_reason: str | None = None
    initiated_by_user_id: str | None = None
    approver_user_id: str | None = None
    experiment_id: str | None = None
    test_id: str | None = None
    spec_hash: str = ""


__all__ = [
    "TerraformRunKind",
    "TerraformRunResult",
    "TerraformRunStatus",
    "TerraformStackSpec",
    "TerraformStateBackend",
]
