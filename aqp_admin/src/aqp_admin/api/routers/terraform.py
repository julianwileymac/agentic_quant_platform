# ruff: noqa: B008, ARG001
"""``/admin/terraform`` — managed Terraform administration.

Metadata is brokered to the AQP monolith because it owns the ORM-backed
Terraform catalogue. Execution is brokered to ``aqp_control_plane`` so
``TerraformRuntime`` remains the only sanctioned plan/apply/destroy path.
"""
from __future__ import annotations

from typing import Any, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/terraform", tags=["terraform"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class TerraformWorkspaceBody(BaseModel):
    slug: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1)
    stack_spec_id: str
    provider_id: str | None = None
    environment: str = "local"
    state_backend: str = "local"
    tenant_org_id: str | None = None
    experiment_id: str | None = None


class TerraformRunBody(BaseModel):
    spec: dict[str, Any]
    extra_args: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
    test_id: str | None = None
    approver_user_id: str | None = None


class TerraformUnlockBody(BaseModel):
    lock_id: str = Field(..., min_length=1)
    approver_note: str | None = None


@router.get("/providers", summary="List Terraform provider records.")
async def list_providers(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.list_terraform_providers(
            bearer_passthrough=_bearer_from_header(authorization)
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/stacks", summary="List Terraform stack specs.")
async def list_stacks(
    module_kind: str | None = None,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.list_terraform_stacks(
            module_kind=module_kind,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/stacks/{stack_id}", summary="Read one Terraform stack spec.")
async def get_stack(
    stack_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.get_terraform_stack(
            stack_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/stacks/{stack_id}/versions", summary="List hash-locked stack versions.")
async def list_stack_versions(
    stack_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.list_terraform_stack_versions(
            stack_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/stacks/{stack_id}/versions/{version_id}",
    summary="Read one hash-locked stack version.",
)
async def get_stack_version(
    stack_id: str,
    version_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.get_terraform_stack_version(
            stack_id,
            version_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/workspaces", summary="List Terraform workspaces.")
async def list_workspaces(
    environment: str | None = None,
    archived: bool = False,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.list_terraform_workspaces(
            environment=environment,
            archived=archived,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post("/workspaces", summary="Create a Terraform workspace metadata row.")
async def create_workspace(
    body: TerraformWorkspaceBody,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.workspace.create")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = body.slug
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.create_terraform_workspace(
            body.model_dump(),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"workspace": result.get("id") or result.get("slug")})
    return {"workspace": result, "audit_run_id": audit.run_id}


@router.get("/workspaces/{workspace_id}", summary="Read one Terraform workspace.")
async def get_workspace(
    workspace_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.get_terraform_workspace(
            workspace_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.delete("/workspaces/{workspace_id}", summary="Archive a Terraform workspace.")
async def archive_workspace(
    workspace_id: str,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.workspace.archive")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = workspace_id
    audit.start(payload={"workspace_id": workspace_id})
    try:
        result = await get_brokers().monolith.archive_terraform_workspace(
            workspace_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"workspace_id": workspace_id})
    return {"result": result, "audit_run_id": audit.run_id}


@router.get("/workspaces/{workspace_id}/state/outputs", summary="Read Terraform outputs.")
async def state_outputs(
    workspace_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.terraform_state_outputs(
            workspace_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post("/workspaces/{workspace_id}/unlock", summary="Unlock a Terraform workspace.")
async def unlock_workspace(
    workspace_id: str,
    body: TerraformUnlockBody,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.workspace.unlock")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = workspace_id
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.unlock_terraform_workspace(
            workspace_id,
            body.model_dump(),
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"workspace_id": workspace_id, "lock_id": body.lock_id})
    return {"result": result, "audit_run_id": audit.run_id}


@router.post(
    "/workspaces/{workspace_id}/{action}",
    summary="Run Terraform plan/validate/apply/destroy through the control plane.",
)
async def run_workspace_action(
    workspace_id: str,
    action: Literal["plan", "validate", "apply", "destroy"],
    body: TerraformRunBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.workspace.run")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    if action in {"apply", "destroy"} and not user.has_scope("admin:cluster"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "error_description": "apply/destroy require admin:cluster",
            },
        )
    audit.target = f"{workspace_id}:{action}"
    payload = body.model_dump()
    audit.start(payload={"workspace_id": workspace_id, "action": action, **payload})
    try:
        result = await get_brokers().control_plane.terraform_run(
            workspace_id,
            action,
            payload,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"workspace_id": workspace_id, "action": action})
    return {"result": result, "audit_run_id": audit.run_id}


@router.get("/runs", summary="List Terraform runs.")
async def list_runs(
    workspace_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.list_terraform_runs(
            workspace_id=workspace_id,
            status_filter=status_filter,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/runs/{run_id}", summary="Read a Terraform run.")
async def get_run(
    run_id: str,
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().monolith.get_terraform_run(
            run_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post("/runs/{run_id}/cancel", summary="Cancel a Terraform run.")
async def cancel_run(
    run_id: str,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.run.cancel")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = run_id
    audit.start(payload={"run_id": run_id})
    try:
        result = await get_brokers().monolith.cancel_terraform_run(
            run_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"run_id": run_id})
    return {"result": result, "audit_run_id": audit.run_id}


@router.get("/halt/status", summary="Inspect the Terraform kill-switch.")
async def halt_status(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    try:
        return await get_brokers().control_plane.terraform_halt_status(
            bearer_passthrough=_bearer_from_header(authorization)
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.delete("/halt", summary="Clear the Terraform kill-switch.")
async def clear_halt(
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.terraform.halt.clear")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = "terraform-halt"
    audit.start(payload={})
    try:
        result = await get_brokers().control_plane.clear_terraform_halt(
            bearer_passthrough=_bearer_from_header(authorization)
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"cleared": True})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
