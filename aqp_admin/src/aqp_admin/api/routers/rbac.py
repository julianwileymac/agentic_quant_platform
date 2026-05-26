# ruff: noqa: B008, ARG001
"""``/admin/rbac`` — RBAC administration on the existing Membership
lattice.

NO Casbin. AQP's canonical RBAC is the four-role lattice
(``aqp-viewer`` / ``aqp-operator`` / ``aqp-admin`` / ``aqp-superadmin``)
defined in
:mod:`aqp_platform_core.auth.rbac` plus the
:class:`Membership` table in the monolith. This router wires the admin
BFF to those existing surfaces:

- list scopes / roles / role expansion (read-only views over
  ``aqp_platform_core.auth.rbac``)
- list memberships (broker to ``data.tenancy.list_memberships``)
- preview-effective-permissions for a given user / org / workspace
  (broker to monolith ``GET /admin/rbac/effective``)
- mutate memberships (broker to monolith — step-up gated)

Per AGENTS rule 27 the admin BFF cannot import :mod:`aqp.*`; it
relies on :mod:`aqp_platform_core.auth.rbac` for the role lattice and
brokers everything else over HTTP.
"""
from __future__ import annotations

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from aqp_platform_core.auth.rbac import expand_role

from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin_scope
from aqp_admin.deps.stepup import require_admin_step_up
from aqp_admin.integrations import AdminBrokerError, get_brokers

router = APIRouter(prefix="/admin/rbac", tags=["rbac"])


# Canonical 4-role lattice — mirrors aqp_platform_core.auth.rbac
_CANONICAL_ROLES = (
    "aqp-viewer",
    "aqp-operator",
    "aqp-admin",
    "aqp-superadmin",
)


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


def _raise_broker_error(exc: AdminBrokerError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code or status.HTTP_502_BAD_GATEWAY,
        detail={"error": exc.code, "error_description": str(exc)},
    ) from exc


class MembershipBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    scope_kind: str = Field(..., pattern=r"^(organization|team|workspace|project)$")
    scope_id: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=4, max_length=200)


class PreviewBody(BaseModel):
    user_id: str = Field(..., min_length=1)
    org_id: str | None = None
    workspace_id: str | None = None


@router.get("/roles", summary="List the canonical role lattice.")
async def list_roles(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
) -> dict[str, Any]:
    """Return the canonical 4-role lattice with expanded scope sets.

    Reads :func:`aqp_platform_core.auth.rbac.expand_role` directly
    so the admin BFF and the monolith always agree on the lattice
    surface — there is no parallel definition.
    """
    return {
        "roles": [
            {
                "role": role,
                "scopes": sorted(expand_role(role)),
            }
            for role in _CANONICAL_ROLES
        ],
    }


@router.get("/scopes", summary="List the canonical scope vocabulary.")
async def list_scopes(
    user: AdminUser = Depends(require_admin_scope("read:infrastructure")),
) -> dict[str, Any]:
    """Return the union of every scope across the lattice.

    Drives the rbac-admin UI's scope-checkbox grid. Order is the
    standard read-write-admin sweep so the UI can render columns
    naturally.
    """
    union: set[str] = set()
    role_to_scopes: dict[str, list[str]] = {}
    for role in _CANONICAL_ROLES:
        scopes = sorted(expand_role(role))
        union.update(scopes)
        role_to_scopes[role] = scopes
    return {
        "scopes": sorted(union),
        "by_role": role_to_scopes,
    }


@router.get("/memberships", summary="List memberships for a scope.")
async def list_memberships(
    organization_id: str | None = None,
    workspace_id: str | None = None,
    role: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """List memberships filtered by scope + optional role.

    Brokers to ``data.tenancy.list_memberships`` (rule 22 boundary).
    """
    try:
        return await get_brokers().monolith.list_memberships(
            organization_id=organization_id,
            workspace_id=workspace_id,
            role=role,
            limit=limit,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post(
    "/effective",
    summary="Preview the effective permissions of a user in a scope.",
)
async def preview_effective(
    body: PreviewBody,
    user: AdminUser = Depends(require_admin_scope("manage:infrastructure")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Compute the effective scope set for a user in a scope.

    Useful in audits ("what can Alice do in workspace W?") and as
    a sanity check before granting a role. The monolith owns the
    union calculation because it has direct access to the
    Membership graph + Auth0 namespaced claim joins.
    """
    try:
        return await get_brokers().monolith.preview_effective_permissions(
            user_id=body.user_id,
            org_id=body.org_id,
            workspace_id=body.workspace_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        _raise_broker_error(exc)


@router.post(
    "/memberships",
    status_code=status.HTTP_201_CREATED,
    summary="Grant a membership.",
)
async def grant_membership(
    body: MembershipBody,
    user: AdminUser = Depends(
        require_admin_step_up("manage:infrastructure", "platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.rbac.grant")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Grant a role binding. Step-up gated per AGENTS rule 52."""
    if body.role not in _CANONICAL_ROLES:
        # Reject non-canonical role assignments at the BFF layer so we
        # don't leak the legacy role names ('viewer' / 'editor' /
        # 'admin' / 'owner') outside the existing translation in
        # aqp.auth.scopes.legacy_role_to_aqp_role.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "unknown_role",
                "error_description": (
                    f"role must be one of {_CANONICAL_ROLES}; "
                    f"legacy role names are translated by the monolith on write"
                ),
            },
        )
    audit.target = f"{body.scope_kind}:{body.scope_id}/{body.user_id}/{body.role}"
    audit.start(payload=body.model_dump())
    try:
        result = await get_brokers().monolith.grant_membership(
            user_id=body.user_id,
            role=body.role,
            scope_kind=body.scope_kind,
            scope_id=body.scope_id,
            reason=body.reason,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"membership_id": result.get("id"), "role": body.role})
    return {"result": result, "audit_run_id": audit.run_id}


@router.delete(
    "/memberships/{membership_id}",
    summary="Revoke a membership.",
)
async def revoke_membership(
    membership_id: str,
    reason: str = Query(..., min_length=4, max_length=200),
    user: AdminUser = Depends(
        require_admin_step_up("manage:infrastructure", "platform:admin", max_age_seconds=180),
    ),
    audit: AuditContext = Depends(audit_context_dep("admin.rbac.revoke")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = membership_id
    audit.start(payload={"reason": reason})
    try:
        result = await get_brokers().monolith.revoke_membership(
            membership_id,
            reason=reason,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except AdminBrokerError as exc:
        audit.fail(str(exc))
        _raise_broker_error(exc)
    audit.succeed({"membership_id": membership_id})
    return {"result": result, "audit_run_id": audit.run_id}


__all__ = ["router"]
