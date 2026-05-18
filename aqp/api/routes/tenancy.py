"""``/tenancy/*`` REST surface for organization / user / Entra-link CRUD.

Mirrors the seven :mod:`aqp.data.mcp.tools.tenancy` DataMCPTools so
the frontend onboarding wizards (OrgCreateWizard,
EntraTenantLinkWizard, UserInviteWizard) have a typed HTTP path that
the existing :class:`Sheet` + :class:`Wizard` components consume
without going through the MCP transport.

Every route is :func:`secure_router`-protected (default scope
``data:read``); write routes additionally call ``require_scope`` /
``require_membership`` per the AGENTS rule-22 contract.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from aqp.api.security import (
    require_authenticated,
    require_membership,
    require_scope,
    secure_router,
)
from aqp.auth import CurrentUser, RequestContext, current_context
from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools.tenancy import (
    CreateOrganizationTool,
    GrantRoleTool,
    InviteUserTool,
    LinkOrgToEntraTenantTool,
    ListMembershipsTool,
    ListOrganizationsTool,
    TransferResourcesTool,
)

logger = logging.getLogger(__name__)


router = secure_router(prefix="/tenancy", tags=["tenancy"])


def _ctx_from_user(
    user: CurrentUser, request_ctx: RequestContext, *, scopes: tuple[str, ...]
) -> MCPToolContext:
    """Build an :class:`MCPToolContext` from the authenticated request."""
    return MCPToolContext(
        actor=user.id,
        actor_kind="user",
        workspace_id=request_ctx.workspace_id,
        project_id=request_ctx.project_id,
        granted_scopes=scopes,
    )


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


@router.get("/organizations")
def list_organizations(
    prefix: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=500),
    user: CurrentUser = Depends(require_authenticated),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = ListOrganizationsTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("data:read",)),
        prefix=prefix,
        status=status_filter,
        limit=limit,
    )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result.error
        )
    return result.data


class CreateOrgPayload(BaseModel):
    name: str = Field(..., min_length=2, max_length=240)
    slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    billing_email: str | None = None
    description: str | None = None
    seed_default_structure: bool = True


@router.post("/organizations")
def create_organization(
    body: CreateOrgPayload,
    user: CurrentUser = Depends(require_scope("tenancy:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = CreateOrganizationTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("tenancy:admin", "data:write")),
        **body.model_dump(),
    )
    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result.error
        )
    return result.data


# ---------------------------------------------------------------------------
# Memberships
# ---------------------------------------------------------------------------


@router.get("/memberships")
def list_memberships(
    user_id: str | None = Query(default=None),
    scope_kind: str | None = Query(default=None),
    scope_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(require_authenticated),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = ListMembershipsTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("data:read",)),
        user_id=user_id,
        scope_kind=scope_kind,
        scope_id=scope_id,
        limit=limit,
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


class GrantRolePayload(BaseModel):
    user_id: str
    scope_kind: str
    scope_id: str
    role: str = "viewer"
    live_control: bool = False
    expires_at_iso: str | None = None


@router.post("/memberships")
def grant_role(
    body: GrantRolePayload,
    user: CurrentUser = Depends(require_scope("tenancy:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = GrantRoleTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("tenancy:admin", "data:write")),
        **body.model_dump(),
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


class InvitePayload(BaseModel):
    email: str
    org_id: str
    role: str = "viewer"
    scope_kind: str = "org"
    scope_id: str | None = None
    display_name: str | None = None
    send_entra_b2b_invitation: bool = True


@router.post("/invites")
def invite_user(
    body: InvitePayload,
    user: CurrentUser = Depends(require_scope("tenancy:invite")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = InviteUserTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("tenancy:invite", "data:write")),
        **body.model_dump(),
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


# ---------------------------------------------------------------------------
# Entra tenant links
# ---------------------------------------------------------------------------


class LinkEntraPayload(BaseModel):
    organization_id: str
    entra_tenant_id: str
    primary_domain: str | None = None
    display_name: str | None = None
    allowed_email_domains: list[str] | None = None
    role_mapping: dict[str, str] | None = None
    activate: bool = True


@router.post("/entra-links")
def link_org_to_entra_tenant(
    body: LinkEntraPayload,
    user: CurrentUser = Depends(require_scope("tenancy:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = LinkOrgToEntraTenantTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("tenancy:admin", "data:write")),
        **body.model_dump(),
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.get("/entra-links")
def list_entra_links(
    organization_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    user: CurrentUser = Depends(require_authenticated),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_terraform import EntraTenantLink

    with get_session() as session:
        q = session.query(EntraTenantLink)
        if organization_id:
            q = q.filter(EntraTenantLink.organization_id == organization_id)
        if status_filter:
            q = q.filter(EntraTenantLink.status == status_filter)
        rows = q.order_by(EntraTenantLink.created_at.desc()).limit(200).all()
        items = [
            {
                "id": r.id,
                "organization_id": r.organization_id,
                "entra_tenant_id": r.entra_tenant_id,
                "primary_domain": r.primary_domain,
                "display_name": r.display_name,
                "status": r.status,
                "allowed_email_domains": r.allowed_email_domains,
                "role_mapping": r.role_mapping,
                "approved_at": r.approved_at.isoformat() if r.approved_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Resource transfer
# ---------------------------------------------------------------------------


class TransferPayload(BaseModel):
    from_org_id: str
    to_org_id: str
    kinds: list[str] = Field(default_factory=list)
    dry_run: bool = True


@router.post("/transfer")
def transfer_resources(
    body: TransferPayload,
    user: CurrentUser = Depends(require_scope("tenancy:admin")),
    ctx: RequestContext = Depends(current_context),
) -> dict[str, Any]:
    tool = TransferResourcesTool()
    result = tool.invoke(
        ctx=_ctx_from_user(user, ctx, scopes=("tenancy:admin", "data:write")),
        **body.model_dump(),
    )
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


__all__ = ["router"]
