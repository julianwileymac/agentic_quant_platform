"""``/manage/terraform`` — Terraform IaC lifecycle (rule-42 relocation).

Phase 0.1 of the control-plane maturation. The CP is now the canonical
owner of the Terraform lifecycle per the modified rule 42; the
monolith brokers via HTTP (the AQP-side broker landing in a follow-up
PR). All mutations route through :class:`TerraformRuntime` so the
audit row is written BEFORE the executor dispatches.

Routes:

- ``POST /manage/terraform/workspaces/{workspace_id}/plan``
- ``POST /manage/terraform/workspaces/{workspace_id}/apply``      (step-up MFA required per rule 52)
- ``POST /manage/terraform/workspaces/{workspace_id}/destroy``    (step-up MFA required)
- ``POST /manage/terraform/workspaces/{workspace_id}/validate``
- ``POST /manage/terraform/halt``                                 (kill-switch fan-out target)
- ``GET  /manage/terraform/halt/status``
- ``GET  /manage/terraform/runs/{run_id}``                        (placeholder; full read is brokered to monolith ledger)

Scopes:

- ``manage:infrastructure`` for plan / validate.
- ``admin:cluster`` for apply / destroy (step-up MFA in production).
- ``admin:cluster`` for halt + clear-halt.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from aqp_platform_core.models.terraform import (
    TerraformRunKind,
    TerraformRunResult,
    TerraformStackSpec,
)
from aqp_platform_core.models.workloads import WorkloadAction

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope
from aqp_cp.services.lifecycle import execute_with_audit
from aqp_cp.settings import get_settings
from aqp_cp.terraform.runtime import (
    TerraformExecutor,
    TerraformRequestContext,
    TerraformRuntime,
    workload_action_for,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["terraform"], prefix="/terraform")

_RUNTIME: TerraformRuntime | None = None


def get_terraform_runtime() -> TerraformRuntime:
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME
    settings = get_settings()
    executor = TerraformExecutor(
        workspaces_dir=settings.terraform_workspaces_dir,
    )
    _RUNTIME = TerraformRuntime(
        executor=executor,
        kill_switch_path=settings.terraform_kill_switch_secret_path,
    )
    return _RUNTIME


class TerraformRunRequest(BaseModel):
    """Inputs to a single Terraform action."""

    spec: TerraformStackSpec
    extra_args: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
    test_id: str | None = None
    approver_user_id: str | None = Field(
        default=None,
        description=(
            "Required for apply / destroy when the workspace's policy "
            "attachment carries 'hard_mandatory' (four-eyes approval). "
            "MUST be a different user from the JWT subject."
        ),
    )


class TerraformHaltRequest(BaseModel):
    reason: str = Field(default="kill-switch", max_length=512)


class TerraformHaltResponse(BaseModel):
    kill_switch_path: str
    reason: str
    triggered_at: datetime
    user_id: str


async def _execute(
    *,
    body: TerraformRunRequest,
    kind: TerraformRunKind,
    user: AuthenticatedUser,
    request_id: str | None,
) -> TerraformRunResult:
    runtime = get_terraform_runtime()
    if kind in (TerraformRunKind.APPLY, TerraformRunKind.DESTROY):
        approver = body.approver_user_id or ""
        if approver and approver == user.sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "approver_must_differ",
                    "error_description": (
                        "approver_user_id must be different from the JWT subject "
                        "for hard_mandatory policy attachments (rule 42 four-eyes)"
                    ),
                },
            )
    ctx = TerraformRequestContext(
        user_id=user.sub,
        org_id=user.org_id,
        workspace_id=user.workspace_id,
        experiment_id=body.experiment_id,
        test_id=body.test_id,
        request_id=request_id,
        approver_user_id=body.approver_user_id,
    )

    async def _do() -> TerraformRunResult:
        return await runtime.execute(
            spec=body.spec,
            kind=kind,
            ctx=ctx,
            extra_args=tuple(body.extra_args),
        )

    _run, result = await execute_with_audit(
        action=workload_action_for(kind),
        target=f"{body.spec.stack_name}/{body.spec.workspace_id}",
        user=user,
        payload={
            "stack_name": body.spec.stack_name,
            "workspace_id": body.spec.workspace_id,
            "state_backend": body.spec.state_backend.value,
            "spec_hash": body.spec.compute_hash(),
            "extra_args": list(body.extra_args),
        },
        fn=_do,
        request_id=request_id,
    )
    return result


@router.post(
    "/workspaces/{workspace_id}/plan",
    summary="Render + run ``terraform plan`` for a workspace.",
    description=(
        "Required scope: ``manage:infrastructure``. Non-mutating; "
        "produces the plan summary that the operator reviews before "
        "applying."
    ),
    response_model=ResponseEnvelope[TerraformRunResult],
)
async def terraform_plan(
    workspace_id: str,
    body: TerraformRunRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("manage:infrastructure")),
) -> ResponseEnvelope[TerraformRunResult]:
    if body.spec.workspace_id != workspace_id:
        body = body.model_copy(
            update={"spec": body.spec.model_copy(update={"workspace_id": workspace_id})}
        )
    result = await _execute(body=body, kind=TerraformRunKind.PLAN, user=user, request_id=x_request_id)
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/workspaces/{workspace_id}/apply",
    summary="Apply a previously-planned Terraform stack (mutating).",
    description=(
        "Required scope: ``admin:cluster``. Step-up MFA required in "
        "production per rule 52. Honours the four-eyes approval "
        "rule (rule 42) — ``approver_user_id`` MUST differ from the "
        "JWT subject when the workspace's policy attachment carries "
        "``hard_mandatory``."
    ),
    response_model=ResponseEnvelope[TerraformRunResult],
)
async def terraform_apply(
    workspace_id: str,
    body: TerraformRunRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[TerraformRunResult]:
    if body.spec.workspace_id != workspace_id:
        body = body.model_copy(
            update={"spec": body.spec.model_copy(update={"workspace_id": workspace_id})}
        )
    result = await _execute(body=body, kind=TerraformRunKind.APPLY, user=user, request_id=x_request_id)
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/workspaces/{workspace_id}/destroy",
    summary="Destroy a Terraform stack (mutating, admin-only).",
    description="Required scope: ``admin:cluster``. Step-up MFA + four-eyes per rule 52.",
    response_model=ResponseEnvelope[TerraformRunResult],
)
async def terraform_destroy(
    workspace_id: str,
    body: TerraformRunRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[TerraformRunResult]:
    if body.spec.workspace_id != workspace_id:
        body = body.model_copy(
            update={"spec": body.spec.model_copy(update={"workspace_id": workspace_id})}
        )
    result = await _execute(body=body, kind=TerraformRunKind.DESTROY, user=user, request_id=x_request_id)
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/workspaces/{workspace_id}/validate",
    summary="Run ``terraform validate`` for a workspace (read-only).",
    response_model=ResponseEnvelope[TerraformRunResult],
)
async def terraform_validate(
    workspace_id: str,
    body: TerraformRunRequest,
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[TerraformRunResult]:
    if body.spec.workspace_id != workspace_id:
        body = body.model_copy(
            update={"spec": body.spec.model_copy(update={"workspace_id": workspace_id})}
        )
    result = await _execute(body=body, kind=TerraformRunKind.VALIDATE, user=user, request_id=x_request_id)
    return ResponseEnvelope(status="ok", data=result)


@router.post(
    "/halt",
    summary="Engage the Terraform kill-switch (mutating; admin-only).",
    description=(
        "Touches the kill-switch sentinel file. Subsequent apply / "
        "destroy requests return ``status='rejected'`` without "
        "invoking the executor until :meth:`/manage/terraform/halt` "
        "is cleared. Mirrors :meth:`/manage/workloads/halt`. "
        "Required scope: ``admin:cluster``."
    ),
    response_model=ResponseEnvelope[TerraformHaltResponse],
)
async def terraform_halt(
    request: Request,
    body: TerraformHaltRequest | None = None,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[TerraformHaltResponse]:
    runtime = get_terraform_runtime()
    reason = (body.reason if body else None) or "kill-switch"
    path = runtime.halt(reason=reason)
    logger.warning(
        "terraform_halt user_id=%s reason=%r path=%s request_id=%s",
        user.sub,
        reason,
        path,
        x_request_id,
    )
    return ResponseEnvelope(
        status="ok",
        data=TerraformHaltResponse(
            kill_switch_path=str(path),
            reason=reason,
            triggered_at=datetime.now(timezone.utc),
            user_id=user.sub,
        ),
    )


@router.delete(
    "/halt",
    summary="Clear the Terraform kill-switch (admin-only).",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def terraform_halt_clear(
    request: Request,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[dict[str, Any]]:
    runtime = get_terraform_runtime()
    runtime.clear_halt()
    return ResponseEnvelope(
        status="ok",
        data={"cleared_at": datetime.now(timezone.utc).isoformat(), "user_id": user.sub},
    )


@router.get(
    "/halt/status",
    summary="Inspect the Terraform kill-switch state.",
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def terraform_halt_status(
    user: AuthenticatedUser = Depends(require_scope("read:infrastructure")),
) -> ResponseEnvelope[dict[str, Any]]:
    runtime = get_terraform_runtime()
    active = runtime.should_halt()
    return ResponseEnvelope(
        status="ok",
        data={
            "active": bool(active),
            "kill_switch_path": str(runtime._kill_switch_path) if runtime._kill_switch_path else None,  # noqa: SLF001
        },
    )


__all__ = ["router", "get_terraform_runtime"]
