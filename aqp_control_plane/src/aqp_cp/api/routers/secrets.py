"""``/manage/secrets`` — rotation + audit (admin:cluster only)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from aqp_cp.auth.deps import AuthenticatedUser, require_scope
from aqp_cp.models import ResponseEnvelope, WorkloadAction
from aqp_cp.services.lifecycle import execute_with_audit
from aqp_cp.services.audit import start_run, finish_run
from aqp_cp.models import WorkloadRunStatus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["secrets"])


@router.post(
    "/secrets/rotate/{service_id}",
    summary="Rotate the secret bound to ``service_id`` (admin:cluster only).",
    description=(
        "Currently a manifest-only operation — emits a WorkloadRun audit row "
        "with the requested rotation target. The actual secret rotation is "
        "delegated to the active credential backend (CredentialResolver), "
        "which is a follow-up PR per cloud provider."
    ),
    response_model=ResponseEnvelope[dict[str, Any]],
)
async def rotate_secret(
    service_id: str,
    secret_name: str,
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[dict[str, Any]]:
    run = start_run(
        action=WorkloadAction.ROTATE_SECRET,
        provider="control-plane",
        target=f"{service_id}/{secret_name}",
        user_id=user.sub,
        request_id=x_request_id,
        org_id=user.org_id,
        workspace_id=user.workspace_id,
        payload={"service_id": service_id, "secret_name": secret_name},
    )
    # Real rotation lands in follow-up PR; record as failed-pending so
    # operators see it in audit + don't think it silently succeeded.
    finish_run(
        run,
        status=WorkloadRunStatus.FAILED,
        error="rotation backend not yet implemented; operator should "
        "trigger the rotation in their secret manager directly",
    )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "error": "rotation_pending",
            "error_description": (
                "Secret rotation backend not yet implemented; rotate "
                "directly in your secret manager (Vault / SSM / Key Vault / "
                "Secret Manager) and re-deploy the service."
            ),
            "audit_run_id": run.run_id,
        },
    )


@router.get(
    "/secrets/audit",
    summary="Audit log of secret-related actions (admin:cluster only).",
    description=(
        "Returns a structured listing of recent secret rotation attempts "
        "(both successful and failed). Today returns an empty stub; the "
        "Postgres-backed audit reader is a follow-up PR."
    ),
    response_model=ResponseEnvelope[list[dict[str, Any]]],
)
async def secrets_audit(
    user: AuthenticatedUser = Depends(require_scope("admin:cluster")),
) -> ResponseEnvelope[list[dict[str, Any]]]:
    return ResponseEnvelope(status="ok", data=[])


__all__ = ["router"]
