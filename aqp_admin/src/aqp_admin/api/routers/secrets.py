# ruff: noqa: B008, ARG001
"""``/admin/secrets`` — secrets-manager surface (read-only + rotate).

Per AGENTS rule 26 + the always-on
`.cursor/rules/aqp-management-engine.mdc` rule:

- The admin BFF NEVER returns plaintext secret values in any response,
  audit row, log line, or websocket frame.
- All operations broker to the control-plane / monolith; the admin
  service has no direct read path into AWS Secrets Manager, Vault,
  or ESO CRDs.
- Rotation requires step-up MFA per AGENTS rule 52.

Read paths:
  GET /admin/secrets                  — list (metadata only: ARN, kind,
                                        consumers, last-rotated)
  GET /admin/secrets/{ref}            — describe one (no value)
  GET /admin/secrets/{ref}/consumers  — pods / services that mount it

Mutating paths:
  POST /admin/secrets/{ref}/rotate    — kicks off a rotation; returns
                                        the rotation_id, never the new
                                        value
"""
from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/secrets", tags=["secrets"])


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class RotateBody(BaseModel):
    """Rotation request — explicit reason for the audit trail."""

    reason: str = Field(..., min_length=4, max_length=200)
    notify_consumers: bool = Field(
        default=True,
        description=(
            "When True the control plane triggers a rolling restart of "
            "the consumer pods so they pick up the new value."
        ),
    )


@router.get("", summary="List secrets (metadata only).")
async def list_secrets(
    backend: str | None = None,
    namespace: str | None = None,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Return metadata for every secret the admin can see.

    Filters by ``backend`` (``aws_secrets_manager`` / ``vault`` /
    ``eso``) and ``namespace``. The response carries ARN / path,
    kind, last-rotated timestamp, and consumer references — never
    the value itself.
    """
    try:
        return await get_brokers().monolith.list_secrets(
            backend=backend,
            namespace=namespace,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get("/{ref:path}", summary="Describe one secret (no value).")
async def describe_secret(
    ref: str,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Describe a single secret by reference (ARN / Vault path / ESO name).

    The response NEVER includes the secret value. It does include
    metadata (kind, version-id, last-rotated, KMS-key-arn, tags,
    consumers).
    """
    try:
        return await get_brokers().monolith.describe_secret(
            ref,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.get(
    "/{ref:path}/consumers",
    summary="List pods / services consuming a secret.",
)
async def list_secret_consumers(
    ref: str,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Report which pods / deployments mount a given secret.

    Drives the rotation impact analysis in the secrets-manager UI.
    """
    try:
        return await get_brokers().monolith.list_secret_consumers(
            ref,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post(
    "/{ref:path}/rotate",
    summary="Rotate a secret (no plaintext returned).",
    status_code=status.HTTP_202_ACCEPTED,
)
async def rotate_secret(
    ref: str,
    body: RotateBody,
    user: AdminUser = Depends(
        require_admin_step_up("manage:infrastructure", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.secrets.rotate")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Trigger rotation of the named secret.

    The response carries the ``rotation_id`` plus the new
    ``version_id`` returned by the backend — NEVER the new secret
    value. Pod consumers are notified by the control plane via a
    rolling restart when ``notify_consumers=True`` (default).
    """
    audit.target = ref
    audit.start(payload={"reason": body.reason, "notify_consumers": body.notify_consumers})
    try:
        result = await get_brokers().monolith.rotate_secret(
            ref,
            reason=body.reason,
            notify_consumers=body.notify_consumers,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed(
        {
            "rotation_id": result.get("rotation_id"),
            "version_id": result.get("version_id"),
            "ref": ref,
        }
    )
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
