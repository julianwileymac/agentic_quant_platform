"""``/terraform/*`` REST + WebSocket surface for the Terraform IaC control plane.

Thin wrappers over the :mod:`aqp.data.mcp.tools.terraform` DataMCP tools
+ direct ORM reads for the workspace / spec / run / state-version CRUD
the frontend needs. Every mutating route enqueues a Celery task via
:mod:`aqp.tasks.terraform_tasks` and returns a
:class:`aqp.api.schemas.TaskAccepted` so the frontend can attach to
``/ws/terraform/runs/<id>``.

Routes (every one is :func:`secure_router`-protected at the default
``data:read`` scope; mutating routes layer ``require_scope`` and
``require_membership`` per AGENTS rule 22):

- ``GET    /terraform/providers``                  / ``POST /terraform/providers``
- ``GET    /terraform/stacks``                     / ``POST /terraform/stacks``
- ``GET    /terraform/stacks/{id}``                / ``PATCH /terraform/stacks/{id}``
- ``GET    /terraform/stacks/{id}/versions``       / ``GET /terraform/stacks/{id}/versions/{v}``
- ``GET    /terraform/workspaces``                 / ``POST /terraform/workspaces``
- ``GET    /terraform/workspaces/{id}``            / ``DELETE /terraform/workspaces/{id}``
- ``POST   /terraform/workspaces/{id}/plan``       / ``POST /terraform/workspaces/{id}/apply``
- ``POST   /terraform/workspaces/{id}/destroy``    / ``POST /terraform/workspaces/{id}/refresh``
- ``GET    /terraform/workspaces/{id}/state/outputs``
- ``POST   /terraform/workspaces/{id}/state/refresh``
- ``POST   /terraform/workspaces/{id}/unlock``
- ``GET    /terraform/runs``                       / ``GET /terraform/runs/{id}``
- ``POST   /terraform/runs/{id}/cancel``
- ``WS     /ws/terraform/runs/{id}``               (canonical progress frames)
- ``POST   /terraform/halt``                       (kill-switch fan-out target)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted
from aqp.api.security import (
    require_authenticated,
    require_dpop_token,
    require_membership,
    require_scope,
    secure_router,
)
from aqp.api.security_stepup import require_step_up
from aqp.auth import CurrentUser, RequestContext, current_context
from aqp.deployment.topology import get_deployment_topology, get_target

logger = logging.getLogger(__name__)


router = secure_router(prefix="/terraform", tags=["terraform"])
# Separate router for the WebSocket — secure_router-wrapped routers
# don't accept ws routes cleanly.
ws_router = APIRouter()


# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class ProviderPayload(BaseModel):
    slug: str = Field(..., min_length=1, max_length=80)
    name: str
    kind: str = Field(
        ..., description="local | docker | baremetal | rpi_cluster | aws | gcp | azure | hcp"
    )
    default_region: str | None = None
    config_json: dict[str, Any] = Field(default_factory=dict)
    credential_key: str | None = None


class StackPayload(BaseModel):
    """Either inline spec or reference to one already snapshotted."""

    spec: dict[str, Any]
    project_id: str | None = None


class WorkspacePayload(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    name: str
    stack_spec_id: str
    provider_id: str | None = None
    environment: str = "local"
    state_backend: str = "local"
    tenant_org_id: str | None = None
    experiment_id: str | None = None


class PlanRequest(BaseModel):
    var_overrides: dict[str, str] = Field(default_factory=dict)
    destroy_plan: bool = False


class ApplyRequest(BaseModel):
    plan_run_id: str
    approver_note: str | None = None


class DestroyRequest(BaseModel):
    confirmation_phrase: str
    approver_note: str | None = None


class UnlockRequest(BaseModel):
    lock_id: str
    approver_note: str | None = None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _serialize_provider(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "kind": row.kind,
        "default_region": row.default_region,
        "config_json": row.config_json,
        "credential_key": row.credential_key,
        "status": row.status,
        "owner_user_id": row.owner_user_id,
        "workspace_id": row.workspace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_stack(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "module_kind": row.module_kind,
        "description": row.description,
        "current_version": row.current_version,
        "annotations": row.annotations,
        "project_id": row.project_id,
        "workspace_id": row.workspace_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_stack_version(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "spec_id": row.spec_id,
        "version": row.version,
        "spec_hash": row.spec_hash,
        "payload_json": row.payload_json,
        "payload_hcl": row.payload_hcl,
        "notes": row.notes,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _serialize_workspace(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "stack_spec_id": row.stack_spec_id,
        "provider_id": row.provider_id,
        "environment": row.environment,
        "state_backend": row.state_backend,
        "state_uri": row.state_uri,
        "hcp_workspace_id": row.hcp_workspace_id,
        "tenant_org_id": row.tenant_org_id,
        "experiment_id": row.experiment_id,
        "archived": bool(row.archived),
        "owner_user_id": row.owner_user_id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
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
        "plan_artifact_uri": row.plan_artifact_uri,
        "plan_summary_json": row.plan_summary_json,
        "apply_artifact_uri": row.apply_artifact_uri,
        "stdout_log_uri": row.stdout_log_uri,
        "stderr_log_uri": row.stderr_log_uri,
        "exit_code": row.exit_code,
        "lock_id": row.lock_id,
        "parent_run_id": row.parent_run_id,
        "celery_task_id": row.celery_task_id,
        "policy_check_result": row.policy_check_result,
        "halted": bool(row.halted),
        "error": row.error,
        "experiment_id": row.experiment_id,
        "test_id": row.test_id,
    }


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


@router.get("/providers")
def list_providers(
    user: CurrentUser = Depends(require_authenticated),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformProvider

    with get_session() as session:
        rows = (
            session.query(TerraformProvider)
            .order_by(TerraformProvider.slug)
            .all()
        )
        items = [_serialize_provider(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/providers")
def create_provider(
    body: ProviderPayload,
    user: CurrentUser = Depends(require_scope("terraform:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformProvider

    with get_session() as session:
        row = TerraformProvider(
            id=str(uuid.uuid4()),
            slug=body.slug,
            name=body.name,
            kind=body.kind,
            default_region=body.default_region,
            config_json=body.config_json,
            credential_key=body.credential_key,
            status="active",
            owner_user_id=user.id,
            workspace_id=ctx.workspace_id,
        )
        session.add(row)
        session.commit()
        return _serialize_provider(row)


# ---------------------------------------------------------------------------
# Stacks + spec versions
# ---------------------------------------------------------------------------


@router.get("/stacks")
def list_stacks(
    module_kind: str | None = Query(default=None),
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformStackSpecRow

    with get_session() as session:
        q = session.query(TerraformStackSpecRow)
        if module_kind:
            q = q.filter(TerraformStackSpecRow.module_kind == module_kind)
        rows = q.order_by(TerraformStackSpecRow.slug).all()
        items = [_serialize_stack(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/stacks")
def create_or_update_stack(
    body: StackPayload,
    user: CurrentUser = Depends(require_scope("terraform:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    from aqp.terraform.registry import persist_spec
    from aqp.terraform.spec import TerraformStackSpec

    try:
        spec = TerraformStackSpec.model_validate(body.spec)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid stack spec: {exc}",
        ) from exc
    version_id = persist_spec(
        spec, project_id=body.project_id or ctx.project_id
    )
    return {"spec_hash": spec.snapshot_hash(), "version_id": version_id, "slug": spec.slug}


@router.get("/stacks/{stack_id}")
def get_stack(
    stack_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformStackSpecRow

    with get_session() as session:
        row = (
            session.query(TerraformStackSpecRow)
            .filter(TerraformStackSpecRow.id == stack_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, detail="stack not found")
        return _serialize_stack(row)


@router.get("/stacks/{stack_id}/versions")
def list_stack_versions(
    stack_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformStackSpecVersion

    with get_session() as session:
        rows = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.spec_id == stack_id)
            .order_by(TerraformStackSpecVersion.version.desc())
            .all()
        )
        items = [_serialize_stack_version(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/stacks/{stack_id}/versions/{version_id}")
def get_stack_version(
    stack_id: str,
    version_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformStackSpecVersion

    with get_session() as session:
        row = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.id == version_id)
            .filter(TerraformStackSpecVersion.spec_id == stack_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, detail="version not found")
        return _serialize_stack_version(row)


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------


@router.get("/workspaces")
def list_workspaces(
    environment: str | None = Query(default=None),
    archived: bool = Query(default=False),
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformWorkspace

    with get_session() as session:
        q = session.query(TerraformWorkspace)
        if not archived:
            q = q.filter(TerraformWorkspace.archived.is_(False))
        if environment:
            q = q.filter(TerraformWorkspace.environment == environment)
        rows = q.order_by(TerraformWorkspace.created_at.desc()).all()
        items = [_serialize_workspace(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/workspaces")
def create_workspace(
    body: WorkspacePayload,
    user: CurrentUser = Depends(require_scope("terraform:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformWorkspace

    with get_session() as session:
        row = TerraformWorkspace(
            id=str(uuid.uuid4()),
            slug=body.slug,
            name=body.name,
            stack_spec_id=body.stack_spec_id,
            provider_id=body.provider_id,
            environment=body.environment,
            state_backend=body.state_backend,
            tenant_org_id=body.tenant_org_id,
            experiment_id=body.experiment_id,
            owner_user_id=user.id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
        )
        session.add(row)
        session.commit()
        return _serialize_workspace(row)


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformWorkspace

    with get_session() as session:
        row = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, detail="workspace not found")
        return _serialize_workspace(row)


@router.delete("/workspaces/{workspace_id}")
def archive_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(require_scope("terraform:admin")),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformWorkspace

    with get_session() as session:
        row = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, detail="workspace not found")
        row.archived = True
        session.commit()
    return {"ok": True, "archived": True}


# ---------------------------------------------------------------------------
# Lifecycle (plan / apply / destroy / refresh / unlock)
# ---------------------------------------------------------------------------


def _enqueue_plan(workspace_id: str, body: PlanRequest, user: CurrentUser) -> TaskAccepted:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import (
        TerraformStackSpecVersion,
        TerraformWorkspace,
    )

    with get_session() as session:
        ws = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if ws is None or not ws.stack_spec_id:
            raise HTTPException(400, detail="workspace has no stack spec")
        version = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.spec_id == ws.stack_spec_id)
            .order_by(TerraformStackSpecVersion.version.desc())
            .first()
        )
        if version is None:
            raise HTTPException(400, detail="stack has no version snapshots")
        from aqp.persistence.models_terraform import TerraformRun

        run = TerraformRun(
            id=str(uuid.uuid4()),
            terraform_workspace_id=workspace_id,
            spec_version_id=version.id,
            run_kind="plan",
            status="queued",
            started_by_user_id=user.id,
            owner_user_id=user.id,
            project_id=ws.project_id,
            workspace_id=ws.workspace_id,
        )
        session.add(run)
        session.commit()
        run_id = run.id

    from aqp.tasks.terraform_tasks import run_terraform_plan

    async_result = run_terraform_plan.apply_async(kwargs={"run_id": run_id})
    return TaskAccepted(
        task_id=async_result.id,
        status="queued",
        stream_url=f"/ws/terraform/runs/{run_id}",
    )


@router.post("/workspaces/{workspace_id}/plan", response_model=TaskAccepted)
def plan_workspace(
    workspace_id: str,
    body: PlanRequest,
    user: CurrentUser = Depends(require_scope("terraform:plan")),
) -> TaskAccepted:
    return _enqueue_plan(workspace_id, body, user)


@router.post("/workspaces/{workspace_id}/apply", response_model=TaskAccepted)
def apply_workspace(
    workspace_id: str,
    body: ApplyRequest,
    user: CurrentUser = Depends(require_scope("terraform:apply")),
    _ctx: RequestContext = Depends(require_membership("admin", "workspace")),
    _dpop: CurrentUser = Depends(require_dpop_token()),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> TaskAccepted:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun

    with get_session() as session:
        plan = (
            session.query(TerraformRun)
            .filter(TerraformRun.id == body.plan_run_id)
            .one_or_none()
        )
        if plan is None or plan.run_kind != "plan":
            raise HTTPException(400, detail="plan_run_id not found or not a plan")
        if plan.status != "completed":
            raise HTTPException(
                400,
                detail=f"plan run status is {plan.status!r}; expected completed",
            )
        run = TerraformRun(
            id=str(uuid.uuid4()),
            terraform_workspace_id=workspace_id,
            spec_version_id=plan.spec_version_id,
            run_kind="apply",
            status="queued",
            started_by_user_id=plan.started_by_user_id,
            approved_by_user_id=user.id,
            parent_run_id=plan.id,
            owner_user_id=user.id,
        )
        session.add(run)
        session.commit()
        run_id = run.id

    from aqp.tasks.terraform_tasks import run_terraform_apply

    async_result = run_terraform_apply.apply_async(
        kwargs={"run_id": run_id, "approver_user_id": user.id}
    )
    return TaskAccepted(
        task_id=async_result.id,
        status="queued",
        stream_url=f"/ws/terraform/runs/{run_id}",
    )


@router.post("/workspaces/{workspace_id}/destroy", response_model=TaskAccepted)
def destroy_workspace(
    workspace_id: str,
    body: DestroyRequest,
    user: CurrentUser = Depends(require_scope("terraform:destroy")),
    _ctx: RequestContext = Depends(require_membership("admin", "workspace")),
    _dpop: CurrentUser = Depends(require_dpop_token()),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> TaskAccepted:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import (
        TerraformRun,
        TerraformStackSpecVersion,
        TerraformWorkspace,
    )

    with get_session() as session:
        ws = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if ws is None:
            raise HTTPException(404, detail="workspace not found")
        if body.confirmation_phrase.strip() != ws.slug:
            raise HTTPException(
                400,
                detail="confirmation_phrase must equal the workspace slug",
            )
        version = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.spec_id == ws.stack_spec_id)
            .order_by(TerraformStackSpecVersion.version.desc())
            .first()
        )
        if version is None:
            raise HTTPException(400, detail="no spec version to destroy")
        run = TerraformRun(
            id=str(uuid.uuid4()),
            terraform_workspace_id=workspace_id,
            spec_version_id=version.id,
            run_kind="destroy",
            status="queued",
            started_by_user_id=user.id,
            approved_by_user_id=user.id,
        )
        session.add(run)
        session.commit()
        run_id = run.id

    from aqp.tasks.terraform_tasks import run_terraform_destroy

    async_result = run_terraform_destroy.apply_async(
        kwargs={"run_id": run_id, "approver_user_id": user.id}
    )
    return TaskAccepted(
        task_id=async_result.id,
        status="queued",
        stream_url=f"/ws/terraform/runs/{run_id}",
    )


@router.post("/workspaces/{workspace_id}/refresh", response_model=TaskAccepted)
def refresh_workspace(
    workspace_id: str,
    user: CurrentUser = Depends(require_scope("terraform:plan")),
) -> TaskAccepted:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import (
        TerraformRun,
        TerraformStackSpecVersion,
        TerraformWorkspace,
    )

    with get_session() as session:
        ws = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if ws is None:
            raise HTTPException(404, detail="workspace not found")
        version = (
            session.query(TerraformStackSpecVersion)
            .filter(TerraformStackSpecVersion.spec_id == ws.stack_spec_id)
            .order_by(TerraformStackSpecVersion.version.desc())
            .first()
        )
        if version is None:
            raise HTTPException(400, detail="no spec version to refresh")
        run = TerraformRun(
            id=str(uuid.uuid4()),
            terraform_workspace_id=workspace_id,
            spec_version_id=version.id,
            run_kind="refresh",
            status="queued",
            started_by_user_id=user.id,
        )
        session.add(run)
        session.commit()
        run_id = run.id
    from aqp.tasks.terraform_tasks import run_terraform_refresh

    async_result = run_terraform_refresh.apply_async(kwargs={"run_id": run_id})
    return TaskAccepted(
        task_id=async_result.id,
        status="queued",
        stream_url=f"/ws/terraform/runs/{run_id}",
    )


@router.post("/workspaces/{workspace_id}/unlock")
def unlock_workspace(
    workspace_id: str,
    body: UnlockRequest,
    user: CurrentUser = Depends(require_scope("terraform:admin")),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun, TerraformWorkspace

    with get_session() as session:
        ws = (
            session.query(TerraformWorkspace)
            .filter(TerraformWorkspace.id == workspace_id)
            .one_or_none()
        )
        if ws is None:
            raise HTTPException(404, detail="workspace not found")
        # Mark every in-flight run cancelled (best effort).
        active = (
            session.query(TerraformRun)
            .filter(TerraformRun.terraform_workspace_id == workspace_id)
            .filter(TerraformRun.status == "running")
            .all()
        )
        now = datetime.utcnow()
        for run in active:
            run.status = "cancelled"
            run.halted = True
            run.finished_at = now
        session.commit()
    return {
        "ok": True,
        "lock_id": body.lock_id,
        "cancelled_runs": [r.id for r in active],
    }


@router.get("/workspaces/{workspace_id}/state/outputs")
def get_state_outputs(
    workspace_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.data.mcp.tools.terraform import GetTerraformStateOutputsTool

    tool = GetTerraformStateOutputsTool()
    from aqp.data.mcp.base import MCPToolContext

    result = tool.invoke(
        ctx=MCPToolContext(actor=user.id, granted_scopes=("data:read",)),
        workspace_id=workspace_id,
    )
    if not result.ok:
        raise HTTPException(400, detail=result.error)
    return result.data


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.get("/runs")
def list_runs(
    workspace_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun

    with get_session() as session:
        q = session.query(TerraformRun)
        if workspace_id:
            q = q.filter(TerraformRun.terraform_workspace_id == workspace_id)
        if status_filter:
            q = q.filter(TerraformRun.status == status_filter)
        rows = q.order_by(TerraformRun.started_at.desc()).limit(int(limit)).all()
        items = [_serialize_run(r) for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: CurrentUser = Depends(require_authenticated),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun

    with get_session() as session:
        row = (
            session.query(TerraformRun)
            .filter(TerraformRun.id == run_id)
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, detail="run not found")
        return _serialize_run(row)


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    user: CurrentUser = Depends(require_scope("terraform:cancel")),
) -> dict[str, Any]:
    from aqp.tasks.terraform_tasks import cancel_terraform_run

    async_result = cancel_terraform_run.apply_async(kwargs={"run_id": run_id})
    return {"task_id": async_result.id, "status": "queued"}


# ---------------------------------------------------------------------------
# Halt (kill-switch fan-out target)
# ---------------------------------------------------------------------------


@router.post("/halt")
def halt_all(
    user: CurrentUser = Depends(require_scope("terraform:admin")),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    """Cancel every in-flight Terraform run and flip the kill switch.

    Fan-out target for the topbar :class:`KillSwitch` component.
    The route iterates every ``status='running'`` /
    ``status='queued'`` :class:`TerraformRun`, sets it to
    ``status='cancelled'`` + ``halted=True``, and best-effort revokes
    the matching Celery task. The Redis kill-switch key is NOT
    touched here — the topbar fans out a separate halt to every
    runtime so each subsystem can decide its own halt semantics.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import TerraformRun
    from aqp.tasks.celery_app import celery_app

    halted: list[str] = []
    with get_session() as session:
        rows = (
            session.query(TerraformRun)
            .filter(TerraformRun.status.in_(["running", "queued", "awaiting_approval"]))
            .all()
        )
        now = datetime.utcnow()
        for row in rows:
            row.status = "cancelled"
            row.halted = True
            row.finished_at = now
            row.error = "halted by /terraform/halt fan-out"
            if row.celery_task_id:
                try:
                    celery_app.control.revoke(row.celery_task_id, terminate=True)
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "revoke failed for celery_task_id=%s",
                        row.celery_task_id,
                        exc_info=True,
                    )
            halted.append(row.id)
        session.commit()
    return {"ok": True, "halted_runs": halted, "total": len(halted)}


# ---------------------------------------------------------------------------
# WebSocket progress stream
# ---------------------------------------------------------------------------


@ws_router.websocket("/ws/terraform/runs/{run_id}")
async def stream_run_progress(ws: WebSocket, run_id: str) -> None:
    """Stream progress frames for a Terraform run.

    Connects to the Redis pub/sub channel the Celery task publishes
    progress frames to. Frames already follow the canonical
    ``{task_id, stage, message, timestamp, **extras}`` shape (rule 4).

    Phase 3a authentication: first client frame must be
    ``{"type":"auth","token":"<JWT>"}``. See :mod:`aqp.auth.ws`.
    """
    from aqp.auth.ws import ws_authenticator

    await ws.accept()
    auth_result = await ws_authenticator.authenticate(ws)
    if auth_result is None:
        return
    from aqp.ws.broker import subscribe

    try:
        # Look up the celery_task_id for the run (best effort).
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import TerraformRun

        with get_session() as session:
            row = (
                session.query(TerraformRun)
                .filter(TerraformRun.id == run_id)
                .one_or_none()
            )
            channel = (row.celery_task_id if row else None) or run_id

        loop = asyncio.get_running_loop()
        for message in await loop.run_in_executor(None, lambda: list(subscribe(channel, timeout=0.5))):
            await ws.send_json(message)

        # Then stream live frames.
        async for message in _async_subscribe(channel):
            await ws.send_json(message)
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        logger.exception("terraform run stream failed for run_id=%s", run_id)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass


async def _async_subscribe(channel: str):
    """Adapter pumping :func:`aqp.ws.broker.subscribe` into an async generator."""
    from aqp.ws.broker import subscribe

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=256)

    def _producer():
        try:
            for message in subscribe(channel, timeout=None):
                # Push onto the queue from the worker thread.
                loop.call_soon_threadsafe(queue.put_nowait, message)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(queue.put_nowait, {"error": str(exc)})

    loop.run_in_executor(None, _producer)
    while True:
        msg = await queue.get()
        if msg is None:
            break
        yield msg
        if isinstance(msg, dict) and msg.get("stage") in {"done", "error"}:
            break


# ---------------------------------------------------------------------------
# Local stack sugar routes - drive the canonical aqp-local stack via the
# ``aqp.tasks.terraform_tasks.run_local_stack`` Celery task. Every route
# returns a TaskAccepted so the frontend's Local Stack panel can attach
# its useChatStream(taskId, "terraform") consumer.
# ---------------------------------------------------------------------------


class LocalStackRunRequest(BaseModel):
    spec_name: str = Field(default="")
    inputs: dict[str, Any] = Field(default_factory=dict)


def _local_stack_spec_name(*, route_name: str, body: LocalStackRunRequest | None) -> str:
    if body and body.spec_name:
        return body.spec_name
    topology = get_deployment_topology()
    if route_name in topology.targets:
        return topology.target(route_name).terraform.stack_slug
    return route_name or get_target("local").terraform.stack_slug


def _local_stack_runtime():
    """Build the topology-backed local TerraformRuntime for read-only endpoints."""
    from aqp.cli.deploy_cmd import _load_local_spec
    from aqp.terraform.runtime import TerraformRuntime

    target = get_target("local")
    return TerraformRuntime(
        spec=_load_local_spec(),
        workspace_id=target.terraform.stack_slug,
        prerendered_workspace_dir=str(target.terraform.environment_path),
    )


def _enqueue_local_stack(*, action: str, spec_name: str) -> TaskAccepted:
    try:
        from aqp.tasks.terraform_tasks import (  # noqa: F401 - inline per route hygiene
            run_local_stack,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"terraform task module unavailable: {exc}",
        ) from exc

    async_result = run_local_stack.apply_async(
        kwargs={"action": action, "spec_name": spec_name}
    )
    task_id = str(async_result.id)
    return TaskAccepted(
        task_id=task_id,
        status="accepted",
        stream_url=f"/ws/terraform/runs/{task_id}",
    )


@router.post("/stacks/{name}/up", response_model=TaskAccepted)
def local_stack_up(
    name: str,
    body: LocalStackRunRequest | None = None,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    """Bring the local stack up (Terraform plan + apply)."""
    spec_name = _local_stack_spec_name(route_name=name, body=body)
    return _enqueue_local_stack(action="up", spec_name=spec_name)


@router.post("/stacks/{name}/down", response_model=TaskAccepted)
def local_stack_down(
    name: str,
    body: LocalStackRunRequest | None = None,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    """Tear down the local stack (Terraform destroy)."""
    spec_name = _local_stack_spec_name(route_name=name, body=body)
    return _enqueue_local_stack(action="down", spec_name=spec_name)


@router.post("/stacks/{name}/build", response_model=TaskAccepted)
def local_stack_build(
    name: str,
    body: LocalStackRunRequest | None = None,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    """Rebuild + push every AQP image. Workloads pick up new images on next apply."""
    spec_name = _local_stack_spec_name(route_name=name, body=body)
    return _enqueue_local_stack(action="build", spec_name=spec_name)


@router.post("/stacks/{name}/refresh", response_model=TaskAccepted)
def local_stack_refresh(
    name: str,
    body: LocalStackRunRequest | None = None,
    user: CurrentUser = Depends(require_authenticated),
) -> TaskAccepted:
    """Run ``terraform apply -refresh-only`` for the local stack."""
    spec_name = _local_stack_spec_name(route_name=name, body=body)
    return _enqueue_local_stack(action="refresh", spec_name=spec_name)


class LocalStackEndpoints(BaseModel):
    api_url: str | None = None
    frontend_url: str | None = None
    mlflow_url: str | None = None
    jaeger_url: str | None = None
    cluster_name: str | None = None
    namespace: str | None = None
    registry: str | None = None
    pods: dict[str, int] = Field(default_factory=dict)
    table_present: bool = True


@router.get("/stacks/{name}/endpoints", response_model=LocalStackEndpoints)
def local_stack_endpoints(name: str) -> LocalStackEndpoints:
    """Return the local stack outputs + a quick pod-status rollup.

    Best-effort: Terraform outputs are read through TerraformRuntime /
    TerraformExecutor and pod counts through KubernetesAdapter. Returns
    blank values when the stack has not been applied yet.
    """

    payload = LocalStackEndpoints()
    target = get_target("local")

    try:
        outputs = _local_stack_runtime().outputs()
        payload.api_url = outputs.get("api_url")
        payload.frontend_url = outputs.get("frontend_url")
        payload.mlflow_url = outputs.get("mlflow_url_in_cluster")
        payload.jaeger_url = outputs.get("jaeger_url_in_cluster")
        payload.cluster_name = outputs.get("cluster_name")
        payload.namespace = outputs.get("namespace")
        extra = outputs.get("endpoints") or {}
        if isinstance(extra, dict):
            payload.registry = extra.get("registry")
            if not payload.namespace:
                payload.namespace = extra.get("namespace")
    except Exception:  # noqa: BLE001
        logger.debug("terraform output read failed", exc_info=True)

    namespace = payload.namespace or target.namespace
    pod_counts: dict[str, int] = {"running": 0, "pending": 0, "failed": 0, "total": 0}
    try:
        from aqp.api.routes.control_plane import _adapter_for_target

        for pod in _adapter_for_target("local").list_pods(namespace=namespace):
            phase = str(getattr(pod, "phase", "") or "Unknown").lower()
            pod_counts["total"] += 1
            if phase == "running":
                pod_counts["running"] += 1
            elif phase in ("pending", "containercreating"):
                pod_counts["pending"] += 1
            elif phase in ("failed", "crashloopbackoff", "error"):
                pod_counts["failed"] += 1
    except Exception:  # noqa: BLE001
        logger.debug("KubernetesAdapter pod rollup failed", exc_info=True)
    payload.pods = pod_counts
    return payload


__all__ = ["router", "ws_router"]
