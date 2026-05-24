"""``/tenancy/invites/*`` invite lifecycle routes.

Protected routes (`router`) are org-admin only and handle create/list/revoke.
The token accept route (`public_router`) is intentionally public — possession
of the raw token is the authorization secret.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from aqp.api.security import secure_router
from aqp.api.security_stepup import require_step_up
from aqp.auth.audit import emit_audit_event
from aqp.auth.deps import current_user, require_role
from aqp.auth.user import CurrentUser, user_can
from aqp.config import settings
from aqp.persistence.db import get_session
from aqp.persistence.models_audit import (
    TenancyInvite,
    generate_invite_token,
    hash_invite_token,
)
from aqp.persistence.models_tenancy import Membership, Organization, Team, User, Workspace

logger = logging.getLogger(__name__)

router = secure_router(prefix="/tenancy/invites", tags=["tenancy", "invites"])
public_router = APIRouter(prefix="/tenancy/invites", tags=["tenancy", "invites"])

_ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "editor": 1,
    "admin": 2,
    "owner": 3,
}


class InviteCreateRequest(BaseModel):
    email: EmailStr
    organization_id: str
    workspace_id: str | None = None
    team_id: str | None = None
    role: Literal["viewer", "editor", "admin", "owner"] = "viewer"
    message: str | None = Field(default=None, max_length=2000)


class InviteCreateResponse(BaseModel):
    id: str
    raw_token: str
    accept_url: str
    organization_id: str
    workspace_id: str | None
    team_id: str | None
    email: str
    role: str
    expires_at: str
    status: str


class InviteSummary(BaseModel):
    id: str
    organization_id: str
    workspace_id: str | None
    team_id: str | None
    email: str
    role: str
    invited_by_user_id: str | None
    invited_by_email: str | None
    token_prefix: str
    status: str
    message: str | None
    expires_at: str
    accepted_at: str | None
    accepted_by_user_id: str | None
    revoked_at: str | None
    revoked_by_user_id: str | None
    created_at: str


class InviteList(BaseModel):
    invites: list[InviteSummary]
    total: int
    page: int
    per_page: int


class InviteAcceptResponse(BaseModel):
    organization_id: str
    organization_name: str
    workspace_id: str | None
    team_id: str | None
    role: str
    email: str
    redirect_url: str
    is_new_user: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    resolved = _as_utc(value)
    if resolved is None:
        return None
    return resolved.isoformat()


def _require_org_admin(user: CurrentUser, organization_id: str) -> None:
    if not user_can(user, "admin", scope_kind="org", scope_id=organization_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role 'admin' required on org {organization_id}",
        )


def _assert_workspace_belongs_to_org(
    *, workspace_id: str, organization_id: str, session: object
) -> None:
    row = (
        session.query(Workspace.org_id)
        .filter(Workspace.id == workspace_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"workspace {workspace_id} not found",
        )
    if row[0] != organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"workspace {workspace_id} does not belong to org {organization_id}",
        )


def _assert_team_belongs_to_org(
    *, team_id: str, organization_id: str, session: object
) -> None:
    row = (
        session.query(Team.org_id)
        .filter(Team.id == team_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"team {team_id} not found",
        )
    if row[0] != organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"team {team_id} does not belong to org {organization_id}",
        )


def _to_summary(invite: TenancyInvite, *, invited_by_email: str | None) -> InviteSummary:
    expires_at = _iso(invite.expires_at)
    created_at = _iso(invite.created_at)
    if not expires_at or not created_at:
        raise RuntimeError(f"Invite {invite.id} has invalid timestamps")
    return InviteSummary(
        id=invite.id,
        organization_id=invite.organization_id,
        workspace_id=invite.workspace_id,
        team_id=invite.team_id,
        email=invite.email,
        role=invite.role,
        invited_by_user_id=invite.invited_by_user_id,
        invited_by_email=invited_by_email,
        token_prefix=invite.token_prefix,
        status=invite.status,
        message=invite.message,
        expires_at=expires_at,
        accepted_at=_iso(invite.accepted_at),
        accepted_by_user_id=invite.accepted_by_user_id,
        revoked_at=_iso(invite.revoked_at),
        revoked_by_user_id=invite.revoked_by_user_id,
        created_at=created_at,
    )


def _invite_scope_targets(invite: TenancyInvite) -> list[tuple[str, str]]:
    targets: list[tuple[str, str]] = [("org", invite.organization_id)]
    if invite.workspace_id:
        targets.append(("workspace", invite.workspace_id))
    if invite.team_id:
        targets.append(("team", invite.team_id))
    return targets


def _upsert_membership(
    *,
    session: object,
    user_id: str,
    scope_kind: str,
    scope_id: str,
    role: str,
    granted_by: str | None,
) -> None:
    role_rank = _ROLE_RANK.get(role, 0)
    rows: list[Membership] = (
        session.query(Membership)
        .filter(
            Membership.user_id == user_id,
            Membership.scope_kind == scope_kind,
            Membership.scope_id == scope_id,
        )
        .all()
    )
    for row in rows:
        if row.role == role:
            return
    if rows:
        strongest = max(rows, key=lambda row: _ROLE_RANK.get(row.role, 0))
        if _ROLE_RANK.get(strongest.role, 0) >= role_rank:
            return
        strongest.role = role
        strongest.live_control = role in {"admin", "owner"}
        return
    session.add(
        Membership(
            user_id=user_id,
            scope_kind=scope_kind,
            scope_id=scope_id,
            role=role,
            live_control=role in {"admin", "owner"},
            granted_by=granted_by,
        )
    )


@router.post("", response_model=InviteCreateResponse)
def create_invite(
    payload: InviteCreateRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    _: object = Depends(require_role("admin", "org")),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> InviteCreateResponse:
    organization_id = payload.organization_id
    _require_org_admin(user, organization_id)
    if payload.role == "owner" and not user_can(
        user, "owner", scope_kind="org", scope_id=organization_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only org owners can grant owner role",
        )

    email = str(payload.email).strip().lower()
    ttl_hours = max(1, int(settings.auth_invite_ttl_hours))
    expires_at = _utcnow() + timedelta(hours=ttl_hours)

    with get_session() as session:
        if payload.workspace_id:
            _assert_workspace_belongs_to_org(
                workspace_id=payload.workspace_id,
                organization_id=organization_id,
                session=session,
            )
        if payload.team_id:
            _assert_team_belongs_to_org(
                team_id=payload.team_id,
                organization_id=organization_id,
                session=session,
            )

        existing = (
            session.query(TenancyInvite)
            .filter(
                TenancyInvite.organization_id == organization_id,
                TenancyInvite.email == email,
                TenancyInvite.status == "pending",
            )
            .one_or_none()
        )
        if existing is not None:
            existing_expires_at = _iso(existing.expires_at)
            if not existing_expires_at:
                raise RuntimeError(f"Invite {existing.id} missing expires_at")
            return InviteCreateResponse(
                id=existing.id,
                raw_token="",
                accept_url="",
                organization_id=existing.organization_id,
                workspace_id=existing.workspace_id,
                team_id=existing.team_id,
                email=existing.email,
                role=existing.role,
                expires_at=existing_expires_at,
                status=existing.status,
            )

        raw_token, token_hash = generate_invite_token()
        invite = TenancyInvite(
            organization_id=organization_id,
            workspace_id=payload.workspace_id,
            team_id=payload.team_id,
            email=email,
            role=payload.role,
            invited_by_user_id=user.id,
            token_hash=token_hash,
            token_prefix=raw_token[:8],
            status="pending",
            message=payload.message,
            expires_at=expires_at,
        )
        session.add(invite)
        session.flush()

        emit_audit_event(
            "invite_create",
            organization_id=organization_id,
            workspace_id=payload.workspace_id,
            actor_user_id=user.id,
            event_category="tenancy",
            source="api",
            request=request,
            details={"email": email, "role": payload.role},
        )

        # TODO(invites): wire into aqp/notifications/email.py once email template lands
        accept_url = f"/onboarding/invite/{raw_token}"
        return InviteCreateResponse(
            id=invite.id,
            raw_token=raw_token,
            accept_url=accept_url,
            organization_id=invite.organization_id,
            workspace_id=invite.workspace_id,
            team_id=invite.team_id,
            email=invite.email,
            role=invite.role,
            expires_at=expires_at.isoformat(),
            status=invite.status,
        )


@router.get("", response_model=InviteList)
def list_invites(
    organization_id: str = Query(...),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=0, ge=0),
    per_page: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(current_user),
    _: object = Depends(require_role("admin", "org")),
) -> InviteList:
    _require_org_admin(user, organization_id)
    with get_session() as session:
        total_query = session.query(TenancyInvite).filter(
            TenancyInvite.organization_id == organization_id
        )
        if status_filter:
            total_query = total_query.filter(TenancyInvite.status == status_filter)
        total = int(total_query.count())

        rows_query = (
            session.query(TenancyInvite, User.email)
            .outerjoin(User, User.id == TenancyInvite.invited_by_user_id)
            .filter(TenancyInvite.organization_id == organization_id)
        )
        if status_filter:
            rows_query = rows_query.filter(TenancyInvite.status == status_filter)
        rows = (
            rows_query.order_by(TenancyInvite.created_at.desc())
            .offset(page * per_page)
            .limit(per_page)
            .all()
        )
        invites = [
            _to_summary(invite, invited_by_email=invited_by_email)
            for invite, invited_by_email in rows
        ]
    return InviteList(invites=invites, total=total, page=page, per_page=per_page)


@router.delete(
    "/{invite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def revoke_invite(
    invite_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    _: object = Depends(require_role("admin", "org")),
    _stepup: CurrentUser = Depends(require_step_up(max_age_seconds=180)),
) -> Response:
    now = _utcnow()
    with get_session() as session:
        invite = (
            session.query(TenancyInvite)
            .filter(TenancyInvite.id == invite_id)
            .one_or_none()
        )
        if invite is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")
        _require_org_admin(user, invite.organization_id)

        previous_status = invite.status
        invite.status = "revoked"
        invite.revoked_at = now
        invite.revoked_by_user_id = user.id

        emit_audit_event(
            "invite_revoke",
            organization_id=invite.organization_id,
            workspace_id=invite.workspace_id,
            actor_user_id=user.id,
            event_category="tenancy",
            source="api",
            request=request,
            details={
                "invite_id": invite.id,
                "email": invite.email,
                "previous_status": previous_status,
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.post("/{token}/accept", response_model=InviteAcceptResponse)
def claim_invite(token: str, request: Request) -> InviteAcceptResponse:
    token_hash = hash_invite_token(token)
    now = _utcnow()

    with get_session() as session:
        invite = (
            session.query(TenancyInvite)
            .filter(TenancyInvite.token_hash == token_hash)
            .one_or_none()
        )
        if invite is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite not found")

        expires_at = _as_utc(invite.expires_at)
        if expires_at is not None and expires_at < now:
            previous_status = invite.status
            invite.status = "expired"
            emit_audit_event(
                "invite_expire",
                organization_id=invite.organization_id,
                workspace_id=invite.workspace_id,
                event_category="tenancy",
                source="api",
                request=request,
                details={
                    "invite_id": invite.id,
                    "email": invite.email,
                    "previous_status": previous_status,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="invite expired or already used",
            )

        if invite.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="invite expired or already used",
            )

        organization = (
            session.query(Organization)
            .filter(Organization.id == invite.organization_id)
            .one_or_none()
        )
        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="organization not found",
            )

        normalized_email = invite.email.strip().lower()
        invitee = (
            session.query(User)
            .filter(User.email == normalized_email)
            .one_or_none()
        )
        is_new_user = invitee is None

        # NOTE: `status` is a free-form String in the schema. The invite lifecycle
        # now includes: pending -> claimed -> accepted (or revoked/expired).
        invite.status = "claimed"

        if is_new_user:
            redirect_url = (
                "/auth/signup"
                f"?invite_token={token}"
                "&return_to=/onboarding/invite-accepted"
                f"&email={quote_plus(normalized_email)}"
            )
        else:
            redirect_url = (
                "/auth/login"
                "?return_to=/onboarding/invite-accepted"
                f"&email={quote_plus(normalized_email)}"
            )

        emit_audit_event(
            "invite_claim",
            user_id=invitee.id if invitee is not None else None,
            organization_id=invite.organization_id,
            workspace_id=invite.workspace_id,
            actor_user_id=invitee.id if invitee is not None else None,
            event_category="tenancy",
            source="api",
            request=request,
            details={
                "invite_id": invite.id,
                "email": normalized_email,
                "is_new_user": is_new_user,
            },
        )

        return InviteAcceptResponse(
            organization_id=invite.organization_id,
            organization_name=organization.name,
            workspace_id=invite.workspace_id,
            team_id=invite.team_id,
            role=invite.role,
            email=normalized_email,
            redirect_url=redirect_url,
            is_new_user=is_new_user,
        )


def mark_invite_accepted(invite_id: str, *, accepted_by_user_id: str) -> None:
    """Finalize a claimed invite after first successful login.

    Called from ``aqp.auth.user.provision_user_from_claims`` when a claimed invite
    is matched to the authenticated user. This creates/updates memberships for the
    invite scopes and transitions ``claimed -> accepted``.
    """
    now = _utcnow()
    with get_session() as session:
        invite = (
            session.query(TenancyInvite)
            .filter(TenancyInvite.id == invite_id)
            .one_or_none()
        )
        if invite is None:
            raise ValueError(f"Invite {invite_id} not found")
        if invite.status != "claimed":
            return

        user_row = (
            session.query(User)
            .filter(User.id == accepted_by_user_id)
            .one_or_none()
        )
        if user_row is None:
            raise ValueError(f"User {accepted_by_user_id} not found")
        if (user_row.email or "").strip().lower() != (invite.email or "").strip().lower():
            raise ValueError("Invite email does not match accepting user")

        for scope_kind, scope_id in _invite_scope_targets(invite):
            _upsert_membership(
                session=session,
                user_id=accepted_by_user_id,
                scope_kind=scope_kind,
                scope_id=scope_id,
                role=invite.role,
                granted_by=invite.invited_by_user_id or accepted_by_user_id,
            )

        invite.status = "accepted"
        invite.accepted_at = now
        invite.accepted_by_user_id = accepted_by_user_id

        emit_audit_event(
            "invite_accept",
            user_id=accepted_by_user_id,
            organization_id=invite.organization_id,
            workspace_id=invite.workspace_id,
            actor_user_id=accepted_by_user_id,
            event_category="tenancy",
            source="api",
            details={
                "invite_id": invite.id,
                "email": invite.email,
                "role": invite.role,
            },
        )

        # TODO(invites): wire this helper into aqp.auth.user.provision_user_from_claims.


__all__ = ["mark_invite_accepted", "public_router", "router"]
