"""``/_internal/msal/sync`` — M2M-secured endpoint for Entra ID / SCIM webhooks.

Mirrors :mod:`aqp.api.routes.auth0_sync`. An Entra ID Logic App /
Provisioning Service / SCIM webhook (or our own MSAL refresh task)
invokes this endpoint to push user lifecycle events into AQP's
:class:`User` + :class:`Membership` tables BEFORE the user signs in
for the first time. This means a freshly-provisioned user lands on a
usable surface on their very first request without a chicken-and-egg
"who-am-I" probe.

Authorization: requires an M2M Bearer token whose audience matches
``settings.auth_m2m_audience``. Unauthenticated requests get a 401.
Re-uses :func:`aqp.api.routes.auth0_sync.require_m2m_token` so the
JWKS / audience / leeway rules stay shared.

AGENTS rule 44: organization provisioning from Entra ID ``tid``
claims goes through :class:`EntraTenantLink`. This endpoint creates a
``pending`` link if it doesn't exist; promotion to ``active`` is an
admin-only operation via the onboarding wizard.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from aqp.api.routes.auth0_sync import require_m2m_token

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/_internal/msal", tags=["msal-sync"])


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class MsalSyncRequest(BaseModel):
    """Payload from an Entra ID Logic App / SCIM webhook.

    The shape mirrors the Microsoft Graph ``user`` resource so an
    upstream Logic App can forward the raw Graph payload directly.
    The endpoint extracts the fields it needs and ignores the rest.
    """

    object_id: str = Field(
        ..., description="Entra ``oid`` — stable user identifier across renames."
    )
    tenant_id: str = Field(
        ..., description="Entra ``tid`` — the user's home tenant id."
    )
    email: str | None = Field(
        default=None, description="Mail or userPrincipalName."
    )
    display_name: str | None = Field(default=None)
    app_roles: list[str] = Field(
        default_factory=list,
        description=(
            "App-role assignments from the Entra application. We map "
            "``aqp.<role>`` entries onto the AQP role lattice."
        ),
    )
    primary_domain: str | None = Field(
        default=None,
        description="Verified primary domain for the tenant (e.g. ``wiley.tech``).",
    )
    lifecycle_event: str = Field(
        default="created",
        description="created | updated | disabled | deleted",
    )


class MsalSyncResponse(BaseModel):
    internal_user_id: str | None = None
    organization_id: str | None = None
    entra_tenant_link_status: str | None = None
    is_new_user: bool = False
    memberships_created: int = 0
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/sync", response_model=MsalSyncResponse)
def msal_sync(
    body: MsalSyncRequest,
    _claims: dict = Depends(require_m2m_token),
) -> MsalSyncResponse:
    """Provision / update an AQP user from an Entra ID upstream event.

    Lifecycle handling:

    - ``created`` / ``updated``: upsert :class:`User`, ensure
      :class:`EntraTenantLink` exists for the tenant, apply
      :class:`Membership` rows derived from the app-role assignments
      (when the link is ``active``).
    - ``disabled``: set ``User.status = "disabled"`` and zero out
      ``live_control`` across every Membership.
    - ``deleted``: same as ``disabled`` but additionally adds a
      ``deleted_at`` timestamp in ``User.meta``.
    """
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import Membership, User
    from aqp.persistence.models_terraform import EntraTenantLink

    notes: list[str] = []
    now = datetime.utcnow()
    auth_subject = body.object_id.strip()
    email = (body.email or "").strip().lower()
    if not email:
        notes.append("no email in payload; user may be unreachable")

    with get_session() as session:
        user = (
            session.query(User)
            .filter(User.auth_subject == auth_subject)
            .one_or_none()
        )
        if user is None and email:
            user = session.query(User).filter(User.email == email).one_or_none()

        is_new = False
        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                email=email or f"unknown-{auth_subject}@local",
                display_name=body.display_name or (email.split("@", 1)[0] if email else auth_subject),
                auth_subject=auth_subject,
                auth_provider="msal_entra",
                status="active",
                meta={
                    "provisioned_via": "msal_sync",
                    "tid": body.tenant_id,
                    "first_seen_at": now.isoformat(),
                },
                last_login_at=None,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            session.flush()
            is_new = True

        # Lifecycle transitions
        if body.lifecycle_event in {"disabled", "deleted"}:
            user.status = "disabled"
            meta = dict(user.meta or {})
            if body.lifecycle_event == "deleted":
                meta["deleted_at"] = now.isoformat()
            user.meta = meta
            session.flush()
            # Strip live_control across the user's memberships.
            for m in session.query(Membership).filter(Membership.user_id == user.id).all():
                m.live_control = False
            session.flush()
            notes.append(f"applied {body.lifecycle_event} lifecycle transition")

        # Upsert EntraTenantLink
        link = (
            session.query(EntraTenantLink)
            .filter(EntraTenantLink.entra_tenant_id == body.tenant_id)
            .one_or_none()
        )
        if link is None:
            link = EntraTenantLink(
                id=str(uuid.uuid4()),
                organization_id=None,
                entra_tenant_id=body.tenant_id,
                primary_domain=body.primary_domain,
                display_name=body.display_name,
                status="pending",
                requested_by_email=email or None,
                meta={"created_via": "msal_sync"},
                created_at=now,
                updated_at=now,
            )
            session.add(link)
            session.flush()
            notes.append("created pending EntraTenantLink; admin must promote")

        memberships_created = 0
        if link.status == "active" and link.organization_id and body.app_roles:
            from aqp.config.defaults import (
                ROLE_ADMIN,
                ROLE_EDITOR,
                ROLE_OWNER,
                ROLE_VIEWER,
                SCOPE_ORG,
            )
            from aqp.persistence.models_tenancy import Membership as MembershipCls

            role_priority = {
                ROLE_VIEWER: 0,
                ROLE_EDITOR: 1,
                ROLE_ADMIN: 2,
                ROLE_OWNER: 3,
            }
            best = ROLE_VIEWER
            for raw in body.app_roles:
                tail = raw.split(".")[-1].lower() if "." in raw else raw.lower()
                if tail in {"owner"}:
                    mapped = ROLE_OWNER
                elif tail in {"admin", "approver"}:
                    mapped = ROLE_ADMIN
                elif tail in {"editor", "operator", "developer"}:
                    mapped = ROLE_EDITOR
                else:
                    mapped = ROLE_VIEWER
                if role_priority[mapped] > role_priority[best]:
                    best = mapped

            existing = (
                session.query(MembershipCls)
                .filter(
                    MembershipCls.user_id == user.id,
                    MembershipCls.scope_kind == SCOPE_ORG,
                    MembershipCls.scope_id == link.organization_id,
                )
                .one_or_none()
            )
            if existing is None:
                session.add(
                    MembershipCls(
                        id=str(uuid.uuid4()),
                        user_id=user.id,
                        scope_kind=SCOPE_ORG,
                        scope_id=link.organization_id,
                        role=best,
                        live_control=best in {ROLE_ADMIN, ROLE_OWNER},
                        granted_by=None,
                        granted_at=now,
                        meta={"granted_via": "msal_sync", "app_roles": list(body.app_roles)},
                    )
                )
                memberships_created += 1
            elif role_priority[best] > role_priority.get(existing.role, 0):
                existing.role = best
                existing.live_control = best in {ROLE_ADMIN, ROLE_OWNER}

            session.flush()
        elif link.status != "active":
            notes.append(
                f"EntraTenantLink status={link.status!r}; memberships deferred until link is active"
            )

        response = MsalSyncResponse(
            internal_user_id=user.id,
            organization_id=link.organization_id,
            entra_tenant_link_status=link.status,
            is_new_user=is_new,
            memberships_created=memberships_created,
            notes=notes,
        )
    return response


__all__ = ["router"]
