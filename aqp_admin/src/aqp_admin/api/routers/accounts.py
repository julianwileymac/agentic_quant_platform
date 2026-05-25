"""``/admin/accounts/*`` — organizations, billing, tenancy.

Audit-first per ``aqp_admin/AGENTS.md`` boundary #2 — every mutating
route writes a row through :class:`AuditContext` BEFORE the action.
Reads are unaudited but still pass through :func:`require_admin` so
the JWT subject is validated.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from aqp_admin.accounts.billing import BillingService
from aqp_admin.accounts.organizations import OrganizationService, OrganizationSummary
from aqp_admin.accounts.tenancy import (
    EntraTenantLink,
    Invite,
    TenancyService,
)
from aqp_admin.deps.audit import AuditContext, audit_context_dep
from aqp_admin.deps.identity import AdminUser, require_admin, require_admin_scope
from aqp_admin.providers.stripe import StripeProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/accounts", tags=["accounts"])

_BILLING_SERVICE = BillingService(providers=(StripeProvider(),))


def _bearer_from_header(header_value: str | None) -> str | None:
    if not header_value or not header_value.lower().startswith("bearer "):
        return None
    return header_value.split(None, 1)[1].strip()


@router.get(
    "/organizations",
    summary="List organizations the caller may administer.",
)
async def list_organizations(
    user: AdminUser = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, list[dict[str, Any]]]:
    service = OrganizationService()
    rows = await service.list(bearer_passthrough=_bearer_from_header(authorization))
    return {"organizations": [_org_to_dict(r) for r in rows]}


@router.get(
    "/organizations/{org_id}",
    summary="Read a single organization with linked namespace status.",
)
async def get_organization(
    org_id: str,
    user: AdminUser = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    service = OrganizationService()
    bearer = _bearer_from_header(authorization)
    org = await service.get(org_id, bearer_passthrough=bearer)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "org_not_found", "org_id": org_id},
        )
    namespace_status = await service.get_tenant_namespace_status(org_id)
    return {
        "organization": _org_to_dict(org),
        "namespace": namespace_status,
    }


@router.get(
    "/billing/summary",
    summary="Aggregated billing summary across registered providers.",
)
async def billing_summary(
    org_id: str,
    period: str = "current",
    user: AdminUser = Depends(require_admin),
) -> dict[str, Any]:
    summaries = await _BILLING_SERVICE.summary_all(org_id, period)
    return {
        "org_id": org_id,
        "period": period,
        "summaries": [
            {
                "provider": s.provider,
                "amount_cents": s.amount_cents,
                "currency": s.currency,
                "line_items": list(s.line_items),
            }
            for s in summaries
        ],
    }


@router.get(
    "/tenancy/invites",
    summary="List pending tenancy invites (optionally scoped to org).",
)
async def list_invites(
    org_id: str | None = None,
    user: AdminUser = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, list[dict[str, Any]]]:
    service = TenancyService()
    rows = await service.list_invites(
        org_id, bearer_passthrough=_bearer_from_header(authorization)
    )
    return {"invites": [_invite_to_dict(r) for r in rows]}


class CreateInviteBody(BaseModel):
    org_id: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    role: str = Field(default="viewer")


@router.post(
    "/tenancy/invites",
    summary="Create a tenancy invite (audit-first).",
)
async def create_invite(
    body: CreateInviteBody,
    user: AdminUser = Depends(require_admin_scope("manage:tenants")),
    audit: AuditContext = Depends(audit_context_dep("admin.tenancy.invites.create")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = f"{body.org_id}/{body.email}"
    audit.start(payload=body.model_dump())
    try:
        service = TenancyService()
        invite = await service.create_invite(
            org_id=body.org_id,
            email=body.email,
            role=body.role,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except Exception as exc:
        audit.fail(str(exc))
        raise
    audit.succeed({"invite_id": invite.id if invite else None})
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "broker_returned_empty"},
        )
    return {"invite": _invite_to_dict(invite)}


@router.get(
    "/tenancy/entra-links",
    summary="List Entra tenant -> Organization links.",
)
async def list_entra_links(
    user: AdminUser = Depends(require_admin),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, list[dict[str, Any]]]:
    service = TenancyService()
    rows = await service.list_entra_links(
        bearer_passthrough=_bearer_from_header(authorization)
    )
    return {"entra_links": [_link_to_dict(r) for r in rows]}


class LinkEntraTenantBody(BaseModel):
    org_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1, description="Microsoft Entra tenant id.")


@router.post(
    "/tenancy/entra-links",
    summary="Promote a pending Entra tenant link (audit-first, admin-only).",
)
async def link_entra_tenant(
    body: LinkEntraTenantBody,
    user: AdminUser = Depends(require_admin_scope("admin:cluster")),
    audit: AuditContext = Depends(audit_context_dep("admin.tenancy.entra_link.promote")),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    audit.target = f"{body.org_id}->{body.tenant_id}"
    audit.start(payload=body.model_dump())
    try:
        service = TenancyService()
        link = await service.link_org_to_entra_tenant(
            org_id=body.org_id,
            tenant_id=body.tenant_id,
            bearer_passthrough=_bearer_from_header(authorization),
        )
    except Exception as exc:
        audit.fail(str(exc))
        raise
    audit.succeed({"link_id": link.id if link else None})
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "broker_returned_empty"},
        )
    return {"entra_link": _link_to_dict(link)}


def _org_to_dict(org: OrganizationSummary) -> dict[str, Any]:
    return {
        "id": org.id,
        "name": org.name,
        "billing_status": org.billing_status,
        "user_count": org.user_count,
        "plan": org.plan,
        "entra_tenant_id": org.entra_tenant_id,
    }


def _invite_to_dict(invite: Invite) -> dict[str, Any]:
    return {
        "id": invite.id,
        "org_id": invite.org_id,
        "email": invite.email,
        "role": invite.role,
        "status": invite.status,
        "expires_at": invite.expires_at,
    }


def _link_to_dict(link: EntraTenantLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "org_id": link.org_id,
        "entra_tenant_id": link.entra_tenant_id,
        "status": link.status,
        "created_at": link.created_at,
    }


__all__ = ["router"]
