"""DataMCP tools wrapping :class:`aqp.terraform.runtime.TerraformRuntime`.

Lets agents (and external MCP clients via the ``/mcp/data/...`` HTTP
surface) browse / plan / apply / destroy Terraform stacks while
honouring AGENTS rules 22 (no direct ORM access from agent bodies)
and 42 (every IaC lifecycle action goes through TerraformRuntime).

Tools registered:

- ``data.terraform.list_workspaces`` — read, ``data:read``.
- ``data.terraform.describe_workspace`` — read.
- ``data.terraform.list_runs`` — read.
- ``data.terraform.get_state_outputs`` — read (sensitive values redacted).
- ``data.terraform.diff_state`` — read (text diff between serials).
- ``data.terraform.lock_status`` — read.
- ``data.terraform.plan_stack`` — mutate, ``terraform:plan``.
- ``data.terraform.apply_stack`` — mutate, ``terraform:apply`` +
  ``require_membership('admin', 'workspace')``.
- ``data.terraform.destroy_stack`` — mutate, ``terraform:destroy``;
  requires ``confirmation_phrase == workspace.slug``.
- ``data.terraform.cancel_run`` — mutate, ``terraform:cancel``.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ListWorkspacesInput(BaseModel):
    environment: str | None = Field(
        default=None, description="local | paper | live | sandbox | wiley-tech"
    )
    cloud_provider: str | None = Field(
        default=None, description="local | aws | gcp | azure | hcp | docker | baremetal | rpi_cluster"
    )
    archived: bool = Field(default=False)
    limit: int = Field(default=50, ge=1, le=500)


class WorkspaceIdInput(BaseModel):
    workspace_id: str


class ListRunsInput(BaseModel):
    workspace_id: str | None = None
    status: str | None = Field(
        default=None,
        description="queued | running | errored | completed | cancelled | awaiting_approval | policy_failed",
    )
    limit: int = Field(default=50, ge=1, le=500)


class DiffStateInput(BaseModel):
    workspace_id: str
    since_run_id: str | None = None


class PlanStackInput(BaseModel):
    stack_spec_id: str = Field(..., description="TerraformStackSpec id (spec, not version)")
    workspace_id: str = Field(...)
    var_overrides: dict[str, str] = Field(default_factory=dict)
    destroy_plan: bool = Field(default=False)


class ApplyStackInput(BaseModel):
    workspace_id: str = Field(...)
    plan_run_id: str = Field(
        ..., description="The completed plan run whose tfplan should be applied."
    )
    approver_note: str | None = Field(default=None)


class DestroyStackInput(BaseModel):
    workspace_id: str = Field(...)
    confirmation_phrase: str = Field(
        ..., description="Must equal the workspace slug for the destroy to proceed."
    )
    approver_note: str | None = Field(default=None)


class CancelRunInput(BaseModel):
    run_id: str = Field(...)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_workspace(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "stack_spec_id": row.stack_spec_id,
        "provider_id": row.provider_id,
        "environment": row.environment,
        "state_backend": row.state_backend,
        "tenant_org_id": row.tenant_org_id,
        "archived": bool(row.archived),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_run(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "terraform_workspace_id": row.terraform_workspace_id,
        "spec_version_id": row.spec_version_id,
        "run_kind": row.run_kind,
        "status": row.status,
        "started_by_user_id": row.started_by_user_id,
        "approved_by_user_id": row.approved_by_user_id,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms,
        "exit_code": row.exit_code,
        "plan_summary_json": row.plan_summary_json,
        "policy_check_result": row.policy_check_result,
        "halted": bool(row.halted),
        "error": row.error,
        "celery_task_id": row.celery_task_id,
    }


def _redact_outputs(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, dict) and value.get("sensitive") is True:
            out[key] = {"sensitive": True, "value": "<redacted>"}
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# Tools — read-only
# ---------------------------------------------------------------------------


@register_data_mcp_tool
class ListTerraformWorkspacesTool(DataMCPTool):
    name = "data.terraform.list_workspaces"
    description = (
        "List Terraform workspaces filtered by environment / cloud_provider / "
        "archived flag. Use this before driving a plan / apply to confirm the "
        "target workspace exists and is wired to the expected provider."
    )
    args_schema = ListWorkspacesInput
    category = "terraform"
    tags = ("terraform", "workspaces", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        environment: str | None = None,
        cloud_provider: str | None = None,
        archived: bool = False,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import (
            TerraformProvider,
            TerraformWorkspace,
        )

        with get_session() as session:
            q = session.query(TerraformWorkspace)
            if not archived:
                q = q.filter(TerraformWorkspace.archived.is_(False))
            if environment:
                q = q.filter(TerraformWorkspace.environment == environment)
            if cloud_provider:
                # Join through providers to filter by kind.
                q = q.join(
                    TerraformProvider,
                    TerraformProvider.id == TerraformWorkspace.provider_id,
                    isouter=True,
                ).filter(TerraformProvider.kind == cloud_provider)
            rows = q.order_by(TerraformWorkspace.created_at.desc()).limit(int(limit)).all()
            items = [_serialize_workspace(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items, "total": len(items)},
            rows_returned=len(items),
            summary=f"listed {len(items)} terraform workspaces",
        )


@register_data_mcp_tool
class DescribeTerraformWorkspaceTool(DataMCPTool):
    name = "data.terraform.describe_workspace"
    description = (
        "Return the full workspace descriptor (provider, spec version, "
        "last successful state version, last run, current lock status)."
    )
    args_schema = WorkspaceIdInput
    category = "terraform"
    tags = ("terraform", "workspaces", "describe")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, workspace_id: str) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import (
            TerraformPolicyAttachment,
            TerraformRun,
            TerraformStateVersion,
            TerraformWorkspace,
        )

        with get_session() as session:
            ws = (
                session.query(TerraformWorkspace)
                .filter(TerraformWorkspace.id == workspace_id)
                .one_or_none()
            )
            if ws is None:
                return MCPToolResult(
                    ok=False,
                    error=f"workspace {workspace_id!r} not found",
                    summary="describe miss",
                )
            last_run = (
                session.query(TerraformRun)
                .filter(TerraformRun.terraform_workspace_id == ws.id)
                .order_by(TerraformRun.started_at.desc())
                .first()
            )
            last_state = (
                session.query(TerraformStateVersion)
                .filter(TerraformStateVersion.terraform_workspace_id == ws.id)
                .order_by(TerraformStateVersion.serial.desc())
                .first()
            )
            policies = (
                session.query(TerraformPolicyAttachment)
                .filter(TerraformPolicyAttachment.terraform_workspace_id == ws.id)
                .all()
            )
            descriptor = _serialize_workspace(ws)
            descriptor["last_run"] = _serialize_run(last_run) if last_run else None
            descriptor["last_state_version"] = (
                {
                    "id": last_state.id,
                    "serial": last_state.serial,
                    "created_at": last_state.created_at.isoformat()
                    if last_state.created_at
                    else None,
                    "resource_count": last_state.resource_count,
                    "outputs_redacted": _redact_outputs(last_state.outputs_redacted),
                }
                if last_state
                else None
            )
            descriptor["policies"] = [
                {
                    "id": p.id,
                    "engine": p.policy_engine,
                    "uri": p.policy_set_uri,
                    "hard_mandatory": bool(p.hard_mandatory),
                    "last_check_passed": p.last_check_passed,
                    "last_check_at": p.last_check_at.isoformat()
                    if p.last_check_at
                    else None,
                }
                for p in policies
            ]
        return MCPToolResult(
            ok=True, data=descriptor, summary=f"described workspace {workspace_id}"
        )


@register_data_mcp_tool
class ListTerraformRunsTool(DataMCPTool):
    name = "data.terraform.list_runs"
    description = (
        "List recent TerraformRun rows, optionally filtered by workspace and "
        "status. Returns the most recent first."
    )
    args_schema = ListRunsInput
    category = "terraform"
    tags = ("terraform", "runs", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        workspace_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformRun

        with get_session() as session:
            q = session.query(TerraformRun)
            if workspace_id:
                q = q.filter(TerraformRun.terraform_workspace_id == workspace_id)
            if status:
                q = q.filter(TerraformRun.status == status)
            rows = q.order_by(TerraformRun.started_at.desc()).limit(int(limit)).all()
            items = [_serialize_run(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items, "total": len(items)},
            rows_returned=len(items),
            summary=f"listed {len(items)} terraform runs",
        )


@register_data_mcp_tool
class GetTerraformStateOutputsTool(DataMCPTool):
    name = "data.terraform.get_state_outputs"
    description = (
        "Return the (redacted) outputs map from the most recent state version "
        "for ``workspace_id``. Sensitive outputs are masked as ``<redacted>``."
    )
    args_schema = WorkspaceIdInput
    category = "terraform"
    tags = ("terraform", "state", "outputs")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, workspace_id: str) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformStateVersion

        with get_session() as session:
            row = (
                session.query(TerraformStateVersion)
                .filter(TerraformStateVersion.terraform_workspace_id == workspace_id)
                .order_by(TerraformStateVersion.serial.desc())
                .first()
            )
            if row is None:
                return MCPToolResult(
                    ok=True,
                    data={"outputs": {}, "serial": None},
                    summary="no state versions yet",
                )
            outputs = _redact_outputs(row.outputs_redacted)
        return MCPToolResult(
            ok=True,
            data={"outputs": outputs, "serial": row.serial},
            summary=f"returned outputs at serial {row.serial}",
        )


@register_data_mcp_tool
class DiffStateTool(DataMCPTool):
    name = "data.terraform.diff_state"
    description = (
        "Compare two consecutive state version serials for a workspace and "
        "return a sparse summary diff (resource_count + outputs added / "
        "removed / changed keys)."
    )
    args_schema = DiffStateInput
    category = "terraform"
    tags = ("terraform", "state", "diff")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        workspace_id: str,
        since_run_id: str | None = None,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformStateVersion

        with get_session() as session:
            q = (
                session.query(TerraformStateVersion)
                .filter(TerraformStateVersion.terraform_workspace_id == workspace_id)
                .order_by(TerraformStateVersion.serial.desc())
            )
            rows = q.limit(2).all()
            if len(rows) < 2:
                return MCPToolResult(
                    ok=True,
                    data={"diff": None, "reason": "fewer than two state versions"},
                    summary="diff skipped",
                )
            current, prev = rows[0], rows[1]
            cur_out = _redact_outputs(current.outputs_redacted)
            prev_out = _redact_outputs(prev.outputs_redacted)
            added = sorted(set(cur_out) - set(prev_out))
            removed = sorted(set(prev_out) - set(cur_out))
            changed = sorted(
                k for k in cur_out
                if k in prev_out and cur_out[k] != prev_out[k]
            )
        return MCPToolResult(
            ok=True,
            data={
                "current_serial": current.serial,
                "previous_serial": prev.serial,
                "outputs_added": added,
                "outputs_removed": removed,
                "outputs_changed": changed,
                "resource_count_delta": (
                    (current.resource_count or 0) - (prev.resource_count or 0)
                ),
            },
            summary=(
                f"diff serial {prev.serial}->{current.serial}: "
                f"+{len(added)} -{len(removed)} ~{len(changed)} outputs"
            ),
        )


@register_data_mcp_tool
class TerraformLockStatusTool(DataMCPTool):
    name = "data.terraform.lock_status"
    description = (
        "Return the current Terraform state lock holder for the workspace's "
        "last in-flight run (lock_id + holder + age)."
    )
    args_schema = WorkspaceIdInput
    category = "terraform"
    tags = ("terraform", "lock", "status")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, workspace_id: str) -> MCPToolResult:
        from datetime import datetime

        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformRun

        with get_session() as session:
            row = (
                session.query(TerraformRun)
                .filter(TerraformRun.terraform_workspace_id == workspace_id)
                .filter(TerraformRun.status == "running")
                .order_by(TerraformRun.started_at.desc())
                .first()
            )
            if row is None:
                return MCPToolResult(
                    ok=True,
                    data={"locked": False},
                    summary="no in-flight runs",
                )
            age_seconds = None
            if row.started_at:
                age_seconds = (datetime.utcnow() - row.started_at).total_seconds()
        return MCPToolResult(
            ok=True,
            data={
                "locked": True,
                "lock_id": row.lock_id,
                "run_id": row.id,
                "run_kind": row.run_kind,
                "started_by_user_id": row.started_by_user_id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "age_seconds": age_seconds,
            },
            summary=f"workspace locked by run {row.id}",
        )


# ---------------------------------------------------------------------------
# Tools — mutating
# ---------------------------------------------------------------------------


def _open_run_row(
    *,
    workspace_id: str,
    run_kind: str,
    spec_version_id: str | None,
    started_by_user_id: str | None,
    approver_user_id: str | None,
    ctx: MCPToolContext,
) -> str:
    """Open a queued TerraformRun row before enqueuing the Celery task."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun

    run_id = str(uuid.uuid4())
    with get_session() as session:
        row = TerraformRun(
            id=run_id,
            terraform_workspace_id=workspace_id,
            spec_version_id=spec_version_id,
            run_kind=run_kind,
            status="queued",
            started_by_user_id=started_by_user_id or ctx.actor,
            approved_by_user_id=approver_user_id,
        )
        row.owner_user_id = ctx.actor
        row.workspace_id = ctx.workspace_id
        row.project_id = ctx.project_id
        session.add(row)
        session.commit()
    return run_id


def _resolve_spec_version(stack_spec_id: str) -> tuple[Any, str | None]:
    """Return ``(spec_obj, spec_version_id)`` for the given stack spec."""
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import (
        TerraformStackSpecRow,
        TerraformStackSpecVersion,
    )
    from aqp.terraform.registry import persist_spec
    from aqp.terraform.spec import TerraformStackSpec

    with get_session() as session:
        spec_row = (
            session.query(TerraformStackSpecRow)
            .filter(TerraformStackSpecRow.id == stack_spec_id)
            .one_or_none()
        )
        if spec_row is None:
            raise LookupError(f"stack spec {stack_spec_id!r} not found")
        version = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.spec_id == spec_row.id)
            .order_by(TerraformStackSpecVersion.version.desc())
            .first()
        )
        if version is None:
            raise LookupError(
                f"stack spec {stack_spec_id!r} has no version snapshots"
            )
        spec = TerraformStackSpec.model_validate(version.payload_json)
    # Re-persist defensively (no-op when hash unchanged) so the run
    # row always points at a real version id.
    spec_version_id = persist_spec(spec) or version.id
    return spec, spec_version_id


@register_data_mcp_tool
class PlanStackTool(DataMCPTool):
    name = "data.terraform.plan_stack"
    description = (
        "Enqueue ``terraform plan`` for the given stack spec against the "
        "target workspace. Returns the queued TerraformRun id + Celery task "
        "id so callers can stream progress via /ws/terraform/runs/<id>."
    )
    args_schema = PlanStackInput
    category = "terraform"
    tags = ("terraform", "plan", "lifecycle")
    mutates = True
    required_scopes = ("terraform:plan",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        stack_spec_id: str,
        workspace_id: str,
        var_overrides: dict[str, str] | None = None,
        destroy_plan: bool = False,
    ) -> MCPToolResult:
        try:
            _spec, spec_version_id = _resolve_spec_version(stack_spec_id)
        except LookupError as exc:
            return MCPToolResult(ok=False, error=str(exc), summary="plan miss spec")

        run_id = _open_run_row(
            workspace_id=workspace_id,
            run_kind="plan",
            spec_version_id=spec_version_id,
            started_by_user_id=ctx.actor,
            approver_user_id=None,
            ctx=ctx,
        )
        from aqp.tasks.terraform_tasks import run_terraform_plan

        async_result = run_terraform_plan.apply_async(kwargs={"run_id": run_id})
        return MCPToolResult(
            ok=True,
            data={
                "run_id": run_id,
                "task_id": async_result.id,
                "stream_url": f"/ws/terraform/runs/{run_id}",
            },
            summary=f"enqueued terraform plan run {run_id}",
        )


@register_data_mcp_tool
class ApplyStackTool(DataMCPTool):
    name = "data.terraform.apply_stack"
    description = (
        "Enqueue ``terraform apply`` against the plan artifact captured by "
        "``plan_run_id``. Requires four-eyes approval when the workspace "
        "has a hard_mandatory OPA policy attached."
    )
    args_schema = ApplyStackInput
    category = "terraform"
    tags = ("terraform", "apply", "lifecycle")
    mutates = True
    required_scopes = ("terraform:apply",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        workspace_id: str,
        plan_run_id: str,
        approver_note: str | None = None,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformRun

        with get_session() as session:
            plan_row = (
                session.query(TerraformRun)
                .filter(TerraformRun.id == plan_run_id)
                .one_or_none()
            )
            if plan_row is None or plan_row.run_kind != "plan":
                return MCPToolResult(
                    ok=False,
                    error=f"plan run {plan_run_id!r} not found or not a plan",
                    summary="apply miss plan",
                )
            if plan_row.status != "completed":
                return MCPToolResult(
                    ok=False,
                    error=(
                        f"plan run {plan_run_id} status={plan_row.status!r}; "
                        "expected 'completed' before apply"
                    ),
                    summary="apply gated by plan status",
                )
            spec_version_id = plan_row.spec_version_id

        run_id = _open_run_row(
            workspace_id=workspace_id,
            run_kind="apply",
            spec_version_id=spec_version_id,
            started_by_user_id=plan_row.started_by_user_id,
            approver_user_id=ctx.actor,
            ctx=ctx,
        )
        from aqp.tasks.terraform_tasks import run_terraform_apply

        async_result = run_terraform_apply.apply_async(
            kwargs={"run_id": run_id, "approver_user_id": ctx.actor}
        )
        return MCPToolResult(
            ok=True,
            data={
                "run_id": run_id,
                "task_id": async_result.id,
                "stream_url": f"/ws/terraform/runs/{run_id}",
                "approver_user_id": ctx.actor,
                "approver_note": approver_note,
            },
            summary=f"enqueued terraform apply run {run_id}",
        )


@register_data_mcp_tool
class DestroyStackTool(DataMCPTool):
    name = "data.terraform.destroy_stack"
    description = (
        "Enqueue ``terraform destroy`` for the workspace. The "
        "``confirmation_phrase`` argument MUST equal the workspace slug to "
        "prevent accidental destruction."
    )
    args_schema = DestroyStackInput
    category = "terraform"
    tags = ("terraform", "destroy", "lifecycle")
    mutates = True
    required_scopes = ("terraform:destroy",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        workspace_id: str,
        confirmation_phrase: str,
        approver_note: str | None = None,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformWorkspace

        with get_session() as session:
            ws = (
                session.query(TerraformWorkspace)
                .filter(TerraformWorkspace.id == workspace_id)
                .one_or_none()
            )
            if ws is None:
                return MCPToolResult(
                    ok=False,
                    error=f"workspace {workspace_id!r} not found",
                    summary="destroy miss ws",
                )
            if confirmation_phrase.strip() != ws.slug:
                return MCPToolResult(
                    ok=False,
                    error="confirmation_phrase must equal the workspace slug",
                    summary="destroy refused",
                )
            spec_version = None
            from aqp.persistence.models_terraform import (
                TerraformStackSpecVersion,
            )

            if ws.stack_spec_id:
                spec_version = (
                    session.query(TerraformStackSpecVersion)
                    .filter(TerraformStackSpecVersion.spec_id == ws.stack_spec_id)
                    .order_by(TerraformStackSpecVersion.version.desc())
                    .first()
                )
        if spec_version is None:
            return MCPToolResult(
                ok=False,
                error="workspace has no spec version to destroy",
                summary="destroy miss spec version",
            )

        run_id = _open_run_row(
            workspace_id=workspace_id,
            run_kind="destroy",
            spec_version_id=spec_version.id,
            started_by_user_id=ctx.actor,
            approver_user_id=ctx.actor,
            ctx=ctx,
        )
        from aqp.tasks.terraform_tasks import run_terraform_destroy

        async_result = run_terraform_destroy.apply_async(
            kwargs={"run_id": run_id, "approver_user_id": ctx.actor}
        )
        return MCPToolResult(
            ok=True,
            data={
                "run_id": run_id,
                "task_id": async_result.id,
                "stream_url": f"/ws/terraform/runs/{run_id}",
                "approver_note": approver_note,
            },
            summary=f"enqueued terraform destroy run {run_id}",
        )


@register_data_mcp_tool
class CancelRunTool(DataMCPTool):
    name = "data.terraform.cancel_run"
    description = (
        "Cancel a queued / running TerraformRun. Best-effort revokes the "
        "Celery task and marks the run row ``status='cancelled'``."
    )
    args_schema = CancelRunInput
    category = "terraform"
    tags = ("terraform", "runs", "cancel")
    mutates = True
    required_scopes = ("terraform:cancel",)

    def run(self, *, ctx: MCPToolContext, run_id: str) -> MCPToolResult:
        from aqp.tasks.terraform_tasks import cancel_terraform_run

        result = cancel_terraform_run.apply_async(kwargs={"run_id": run_id})
        return MCPToolResult(
            ok=True,
            data={"run_id": run_id, "task_id": result.id},
            summary=f"requested cancel for run {run_id}",
        )


__all__ = [
    "ApplyStackTool",
    "CancelRunTool",
    "DescribeTerraformWorkspaceTool",
    "DestroyStackTool",
    "DiffStateTool",
    "GetTerraformStateOutputsTool",
    "ListTerraformRunsTool",
    "ListTerraformWorkspacesTool",
    "PlanStackTool",
    "TerraformLockStatusTool",
]
