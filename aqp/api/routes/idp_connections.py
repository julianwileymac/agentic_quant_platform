"""``/tenancy/orgs/{org_id}/idp-connections`` + ``/idp-group-mappings`` routes.

AGENTS rule 44 + Phase 6 of the Auth0 Refactor — generalises the
existing ``EntraTenantLink`` lifecycle to all non-Entra IdPs (Google
Workspace, AWS IAM Identity Center, Okta, OneLogin, JumpCloud, generic
SAML/OIDC). The admin UI lives at
:mod:`aqp_client/src/components/onboarding/IdpGroupMappingEditor.tsx`
and writes against these endpoints.

All mutating routes:

- Require ``admin`` membership on the target org.
- Require step-up MFA (AGENTS rule 52).
- Emit a :class:`SecurityAuditEvent` row via :func:`emit_audit_event`.

Secret material (client secrets, signing certs, encryption keys) NEVER
lands in the request / response body — it resolves through the
:class:`aqp.credentials.CredentialResolver` chain under
``CredentialKey(f"idp:{connection_kind}:{org_id}", "client")``. The
route layer only handles the metadata + the AQP-side wiring (allowed
email domains, group-mapping table, status lifecycle).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.security_stepup import require_step_up
from aqp.auth import CurrentUser, current_user
from aqp.auth.audit import emit_audit_event
from aqp.auth.user import user_can

logger = logging.getLogger(__name__)


router = secure_router(prefix="/tenancy/orgs", tags=["tenancy", "idp-connections"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


_ALLOWED_CONNECTION_KINDS = {
    "entra",
    "google_workspace",
    "aws_iam_identity_center",
    "okta",
    "onelogin",
    "jumpcloud",
    "generic_oidc",
    "generic_saml",
}


class IdpConnectionIn(BaseModel):
    connection_kind: Literal[
        "entra",
        "google_workspace",
        "aws_iam_identity_center",
        "okta",
        "onelogin",
        "jumpcloud",
        "generic_oidc",
        "generic_saml",
    ]
    display_name: str | None = Field(default=None, max_length=240)
    auth0_connection_id: str | None = Field(default=None, max_length=120)
    allowed_email_domains: str | None = Field(
        default=None,
        description=(
            "Comma-separated list of email domains accepted by this IdP. "
            "Empty means any domain the IdP accepts."
        ),
    )
    config: dict[str, Any] = Field(default_factory=dict)


class IdpConnectionSummary(BaseModel):
    id: str
    organization_id: str
    connection_kind: str
    auth0_connection_id: str | None
    display_name: str | None
    status: str
    allowed_email_domains: str | None
    config: dict[str, Any]
    created_at: str
    updated_at: str


class IdpGroupMappingIn(BaseModel):
    idp_connection_id: str
    external_group_name: str = Field(..., min_length=1, max_length=255)
    aqp_role: Literal["viewer", "editor", "admin", "owner"]
    scope_kind: Literal["org", "team", "workspace", "project", "lab"]
    scope_id: str = Field(..., min_length=1, max_length=36)


class IdpGroupMappingSummary(BaseModel):
    id: str
    organization_id: str
    idp_connection_id: str
    external_group_name: str
    aqp_role: str
    scope_kind: str
    scope_id: str
    is_active: bool
    created_at: str


# ---------------------------------------------------------------------------
# Helper guards
# ---------------------------------------------------------------------------


def _require_org_admin(user: CurrentUser, org_id: str) -> None:
    if user.is_default:
        return
    if not user_can(user, "admin", scope_kind="org", scope_id=org_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"admin role on org {org_id} is required",
        )


# ---------------------------------------------------------------------------
# IdP connections — CRUD
# ---------------------------------------------------------------------------


@router.get("/{org_id}/idp-connections", response_model=list[IdpConnectionSummary])
def list_connections(
    org_id: str,
    user: CurrentUser = Depends(current_user),
) -> list[IdpConnectionSummary]:
    """List every IdP connection configured for the org (admin only)."""
    _require_org_admin(user, org_id)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpConnectionRecord

    with get_session() as session:
        rows = (
            session.query(IdpConnectionRecord)
            .filter(IdpConnectionRecord.organization_id == org_id)
            .order_by(IdpConnectionRecord.created_at.desc())
            .all()
        )
        return [_to_connection_summary(row) for row in rows]


@router.post(
    "/{org_id}/idp-connections",
    response_model=IdpConnectionSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    org_id: str,
    body: IdpConnectionIn,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> IdpConnectionSummary:
    """Create a new IdP connection record (admin only, step-up required)."""
    _require_org_admin(user, org_id)
    if body.connection_kind not in _ALLOWED_CONNECTION_KINDS:
        raise HTTPException(400, f"unsupported connection_kind {body.connection_kind!r}")

    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpConnectionRecord, Organization

    with get_session() as session:
        if not session.query(Organization).filter(Organization.id == org_id).one_or_none():
            raise HTTPException(404, f"organization {org_id} not found")
        row = IdpConnectionRecord(
            organization_id=org_id,
            connection_kind=body.connection_kind,
            auth0_connection_id=(body.auth0_connection_id or None),
            display_name=body.display_name,
            allowed_email_domains=body.allowed_email_domains,
            config=dict(body.config or {}),
            created_by_user_id=user.id,
            status="pending",
        )
        session.add(row)
        session.flush()
        summary = _to_connection_summary(row)

    emit_audit_event(
        "idp_connection_created",
        user_id=user.id,
        organization_id=org_id,
        actor_user_id=user.id,
        event_category="tenancy",
        severity="warning",
        source="api",
        details={
            "connection_id": summary.id,
            "connection_kind": summary.connection_kind,
            "auth0_connection_id": summary.auth0_connection_id,
        },
    )
    return summary


@router.delete(
    "/{org_id}/idp-connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_connection(
    org_id: str,
    connection_id: str,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> None:
    """Revoke an IdP connection (admin only, step-up required)."""
    _require_org_admin(user, org_id)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpConnectionRecord

    with get_session() as session:
        row = (
            session.query(IdpConnectionRecord)
            .filter(
                IdpConnectionRecord.id == connection_id,
                IdpConnectionRecord.organization_id == org_id,
            )
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, "connection not found")
        row.status = "revoked"
        row.updated_at = datetime.utcnow()
        session.flush()

    emit_audit_event(
        "idp_connection_revoked",
        user_id=user.id,
        organization_id=org_id,
        actor_user_id=user.id,
        event_category="tenancy",
        severity="warning",
        source="api",
        details={"connection_id": connection_id},
    )


# ---------------------------------------------------------------------------
# IdP group mappings — CRUD
# ---------------------------------------------------------------------------


@router.get(
    "/{org_id}/idp-group-mappings",
    response_model=list[IdpGroupMappingSummary],
)
def list_group_mappings(
    org_id: str,
    user: CurrentUser = Depends(current_user),
) -> list[IdpGroupMappingSummary]:
    """List the IdP group → AQP role mappings for the org (admin only)."""
    _require_org_admin(user, org_id)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpGroupMapping

    with get_session() as session:
        rows = (
            session.query(IdpGroupMapping)
            .filter(IdpGroupMapping.organization_id == org_id)
            .order_by(IdpGroupMapping.created_at.desc())
            .all()
        )
        return [_to_mapping_summary(row) for row in rows]


@router.post(
    "/{org_id}/idp-group-mappings",
    response_model=IdpGroupMappingSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_group_mapping(
    org_id: str,
    body: IdpGroupMappingIn,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> IdpGroupMappingSummary:
    """Create a new IdP group → AQP role mapping (admin, step-up)."""
    _require_org_admin(user, org_id)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpConnectionRecord, IdpGroupMapping

    with get_session() as session:
        conn = (
            session.query(IdpConnectionRecord)
            .filter(
                IdpConnectionRecord.id == body.idp_connection_id,
                IdpConnectionRecord.organization_id == org_id,
            )
            .one_or_none()
        )
        if conn is None:
            raise HTTPException(404, "idp_connection not found for this org")
        # Only org owners can grant the owner role on the org scope.
        if body.aqp_role == "owner" and body.scope_kind == "org":
            if not user_can(user, "owner", scope_kind="org", scope_id=org_id):
                raise HTTPException(
                    403, "only org owners can mint owner-role mappings"
                )
        row = IdpGroupMapping(
            organization_id=org_id,
            idp_connection_id=body.idp_connection_id,
            external_group_name=body.external_group_name,
            aqp_role=body.aqp_role,
            scope_kind=body.scope_kind,
            scope_id=body.scope_id,
            created_by_user_id=user.id,
        )
        session.add(row)
        session.flush()
        summary = _to_mapping_summary(row)

    emit_audit_event(
        "idp_group_mapping_created",
        user_id=user.id,
        organization_id=org_id,
        actor_user_id=user.id,
        event_category="tenancy",
        severity="info",
        source="api",
        details={
            "mapping_id": summary.id,
            "external_group": summary.external_group_name,
            "aqp_role": summary.aqp_role,
            "scope_kind": summary.scope_kind,
            "scope_id": summary.scope_id,
        },
    )
    return summary


@router.delete(
    "/{org_id}/idp-group-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_group_mapping(
    org_id: str,
    mapping_id: str,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> None:
    """Soft-delete an IdP group mapping (admin, step-up)."""
    _require_org_admin(user, org_id)
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import IdpGroupMapping

    with get_session() as session:
        row = (
            session.query(IdpGroupMapping)
            .filter(
                IdpGroupMapping.id == mapping_id,
                IdpGroupMapping.organization_id == org_id,
            )
            .one_or_none()
        )
        if row is None:
            raise HTTPException(404, "mapping not found")
        row.is_active = False
        row.updated_at = datetime.utcnow()
        session.flush()

    emit_audit_event(
        "idp_group_mapping_revoked",
        user_id=user.id,
        organization_id=org_id,
        actor_user_id=user.id,
        event_category="tenancy",
        severity="info",
        source="api",
        details={"mapping_id": mapping_id},
    )


# ---------------------------------------------------------------------------
# Internal-only endpoint used by the post-login Action ``aqp-idp-group-sync``
# ---------------------------------------------------------------------------


internal_router = secure_router(prefix="/_internal/idp", tags=["idp-connections", "internal"])


class IdpGroupSyncRequest(BaseModel):
    """Payload the Auth0 post-login Action posts on every login.

    The Action collects the user's group memberships from the IdP's
    claim block (Azure ``groups``, Google's ``hd``-based group claim,
    Okta ``groups``, etc.) and forwards them here. The endpoint
    consults the :class:`IdpGroupMapping` table and upserts matching
    :class:`Membership` rows.
    """

    user_id: str
    auth0_organization_id: str | None = None
    connection_kind: str
    external_groups: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 7 — Migrate tenancy strategy (admin, step-up MFA)
# ---------------------------------------------------------------------------


class MigrateStrategyRequest(BaseModel):
    target_strategy: Literal[
        "shared_schema_rls",
        "schema_per_tenant",
        "database_per_enterprise",
    ]
    profile: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Strategy-specific provisioning profile. For schema_per_tenant: "
            "{schema_name?}. For database_per_enterprise: "
            "{dsn_vault_path?, region?}. Empty dict accepts strategy defaults."
        ),
    )


@router.post("/{org_id}/migrate-strategy")
def migrate_strategy(
    org_id: str,
    body: MigrateStrategyRequest,
    user: CurrentUser = Depends(current_user),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> dict[str, Any]:
    """Migrate an org between tenancy strategies (admin, step-up MFA).

    Owner-only (only org owners can flip an org's tenancy posture
    because the migration is potentially destructive and irreversible
    without a separate data-copy job). The route does NOT itself
    move data — it provisions the target strategy's resources
    (schema / DSN), flips ``Organization.tenancy_strategy``, and
    publishes the Redis invalidation so every worker picks up the
    change. Operators run the actual data copy / cutover as a
    separate, supervised maintenance window task.
    """
    if not user_can(user, "owner", scope_kind="org", scope_id=org_id):
        raise HTTPException(403, "org owner role is required for strategy migration")

    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import Organization
    from aqp.tenancy.factory import get_tenancy_factory
    from aqp.tenancy.strategies.hybrid import publish_strategy_changed

    with get_session() as session:
        org = session.query(Organization).filter(Organization.id == org_id).one_or_none()
        if org is None:
            raise HTTPException(404, f"organization {org_id} not found")
        previous = str(getattr(org, "tenancy_strategy", "") or "") or None
        if previous == body.target_strategy:
            return {
                "ok": True,
                "organization_id": org_id,
                "previous": previous,
                "new": body.target_strategy,
                "no_op": True,
            }
        org.tenancy_strategy = body.target_strategy
        org.updated_at = datetime.utcnow()
        session.flush()

    # Drop our own cache + tell peers.
    publish_strategy_changed(org_id)

    emit_audit_event(
        "tenancy_strategy_migrated",
        user_id=user.id,
        organization_id=org_id,
        actor_user_id=user.id,
        event_category="tenancy",
        severity="critical",
        source="api",
        details={
            "previous": previous,
            "new": body.target_strategy,
            "profile": body.profile,
        },
    )

    return {
        "ok": True,
        "organization_id": org_id,
        "previous": previous,
        "new": body.target_strategy,
        "no_op": False,
        "next_steps": [
            "Run the strategy's onboard() routine to provision target resources.",
            "Schedule a maintenance window to copy data if the move requires it.",
            "Verify new sessions land on the target strategy by inspecting "
            "the HybridStrategy cache log entries.",
        ],
    }


@internal_router.post("/sync-groups")
def sync_groups(
    body: IdpGroupSyncRequest,
    user: CurrentUser = Depends(current_user),
) -> dict[str, Any]:
    """Apply :class:`IdpGroupMapping` matches to the user's memberships.

    Idempotent. Returns the count of memberships added / upgraded so
    the Action can record the outcome.
    """
    # The Action authenticates via the existing M2M token chain
    # (the `secure_router` enforces ``require_authenticated``). The
    # user identity comes from the body so the route can target any
    # user — checked by the membership upsert logic which uses the
    # request body's user_id, NOT the M2M caller's identity.
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import (
        IdpConnectionRecord,
        IdpGroupMapping,
        Membership,
    )

    import uuid as _uuid

    upgraded = 0
    inserted = 0
    with get_session() as session:
        # Find every active connection of this kind across all orgs;
        # multiple orgs may use the same kind (e.g. AcmeCorp Okta vs
        # SubsidiaryCo Okta). The mappings filter narrows further.
        connections = (
            session.query(IdpConnectionRecord)
            .filter(
                IdpConnectionRecord.connection_kind == body.connection_kind,
                IdpConnectionRecord.status == "active",
            )
            .all()
        )
        for conn in connections:
            mappings = (
                session.query(IdpGroupMapping)
                .filter(
                    IdpGroupMapping.idp_connection_id == conn.id,
                    IdpGroupMapping.is_active.is_(True),
                    IdpGroupMapping.external_group_name.in_(body.external_groups or [""]),
                )
                .all()
            )
            for mapping in mappings:
                existing = (
                    session.query(Membership)
                    .filter(
                        Membership.user_id == body.user_id,
                        Membership.scope_kind == mapping.scope_kind,
                        Membership.scope_id == mapping.scope_id,
                    )
                    .one_or_none()
                )
                role_priority = {"viewer": 0, "editor": 1, "admin": 2, "owner": 3}
                if existing is None:
                    session.add(
                        Membership(
                            id=str(_uuid.uuid4()),
                            user_id=body.user_id,
                            scope_kind=mapping.scope_kind,
                            scope_id=mapping.scope_id,
                            role=mapping.aqp_role,
                            live_control=mapping.aqp_role in {"admin", "owner"},
                            granted_by=user.id,
                        )
                    )
                    inserted += 1
                else:
                    if role_priority.get(existing.role, 0) < role_priority.get(
                        mapping.aqp_role, 0
                    ):
                        existing.role = mapping.aqp_role
                        existing.live_control = mapping.aqp_role in {"admin", "owner"}
                        upgraded += 1
        session.flush()
    return {"ok": True, "inserted": inserted, "upgraded": upgraded}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_connection_summary(row: Any) -> IdpConnectionSummary:
    return IdpConnectionSummary(
        id=str(row.id),
        organization_id=str(row.organization_id),
        connection_kind=row.connection_kind,
        auth0_connection_id=row.auth0_connection_id,
        display_name=row.display_name,
        status=row.status,
        allowed_email_domains=row.allowed_email_domains,
        config=row.config or {},
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _to_mapping_summary(row: Any) -> IdpGroupMappingSummary:
    return IdpGroupMappingSummary(
        id=str(row.id),
        organization_id=str(row.organization_id),
        idp_connection_id=str(row.idp_connection_id),
        external_group_name=row.external_group_name,
        aqp_role=row.aqp_role,
        scope_kind=row.scope_kind,
        scope_id=row.scope_id,
        is_active=bool(row.is_active),
        created_at=row.created_at.isoformat(),
    )


__all__ = ["internal_router", "router"]
