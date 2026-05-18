"""Authenticated account-management surface under ``/me/*``."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from aqp.api.security import secure_router
from aqp.auth.context import RequestContext
from aqp.auth.deps import current_context, current_user
from aqp.auth.user import CurrentUser

logger = logging.getLogger(__name__)
router = secure_router(prefix="/me", tags=["account", "me"])


class MeProfile(BaseModel):
    id: str
    email: str
    display_name: str
    auth_provider: str
    auth_subject: str | None
    picture: str | None
    avatar_url: str | None
    is_default: bool
    created_at: str | None
    last_login_at: str | None
    auth0_user_id: str | None
    email_verified: bool | None
    mfa_enabled: bool
    factor_count: int
    session_count: int
    connection: str | None
    connected_account_count: int
    workspace_count: int
    project_count: int
    lab_count: int


class UpdateMeRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=2048)
    picture: str | None = Field(default=None, max_length=2048)


class ChangePasswordRequest(BaseModel):
    return_url: str = Field(..., max_length=2048)


class ChangePasswordResponse(BaseModel):
    ticket_url: str
    expires_at: str


class MfaFactor(BaseModel):
    id: str
    type: str
    name: str | None
    enrolled_at: str
    confirmed: bool
    phone_number: str | None


class MfaEnrollRequest(BaseModel):
    factor: Literal["totp", "sms", "webauthn-roaming", "webauthn-platform", "push"]
    return_url: str | None = None


class MfaEnrollment(BaseModel):
    ticket_id: str
    ticket_url: str
    qr_code_url: str | None
    secret: str | None
    recovery_codes: list[str]
    expires_at: str


class Session(BaseModel):
    id: str
    user_id: str
    created_at: str
    updated_at: str
    last_activity: str | None
    ip: str | None
    user_agent: str | None
    device: str | None
    location: str | None
    is_current: bool = False


class RevokeAllSessionsResponse(BaseModel):
    revoked: int


class ConnectedAccount(BaseModel):
    provider: str
    connection: str
    user_id: str
    profile_data: dict[str, Any] = Field(default_factory=dict)
    is_primary: bool
    is_social: bool = False


class LinkAccountRequest(BaseModel):
    secondary_jwt: str = Field(
        ...,
        description="Bearer token from the user's other-account login",
        min_length=1,
    )


class LinkAccountResponse(BaseModel):
    link_url: str
    state: str


class UnlinkAccountRequest(BaseModel):
    provider: str = Field(..., min_length=1)


class AuditEvent(BaseModel):
    id: str
    date: str
    event_type: str
    event_category: str
    severity: str
    source: str
    ip: str | None
    user_agent: str | None
    connection: str | None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    events: list[AuditEvent]
    total: int
    page: int
    per_page: int
    warnings: list[str] = Field(
        default_factory=list,
        alias="_warnings",
        serialization_alias="_warnings",
    )


class DeleteMeResponse(BaseModel):
    status: Literal["deleted"]


def _is_auth0_subject(subject: str | None) -> bool:
    """Heuristic: does `subject` look like an Auth0 user id?"""
    if not subject:
        return False
    return "|" in subject


def _get_management_client_or_502():
    """Return the management client, or raise 502 if not configured."""
    from aqp.auth.management_api import Auth0ManagementError, get_management_client

    try:
        return get_management_client()
    except Auth0ManagementError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Auth0 Management API not configured: {exc}",
        ) from exc


def _wrap_management_call(callable_, *args, **kwargs):
    """Call `callable_(*args, **kwargs)` and map Auth0ManagementError to HTTPException."""
    from aqp.auth.management_api import Auth0ManagementError

    try:
        return callable_(*args, **kwargs)
    except Auth0ManagementError as exc:
        message = str(exc)
        lower = message.lower()
        if "not found" in lower:
            raise HTTPException(status_code=404, detail=message) from exc
        if "rate limit" in lower:
            raise HTTPException(status_code=429, detail=message) from exc
        if "scope" in lower and "required" in lower:
            raise HTTPException(
                status_code=502,
                detail=f"Auth0 Management API scope missing: {exc}",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=f"Auth0 Management API error: {exc}",
        ) from exc


def _require_auth0_user_id(user: CurrentUser) -> str:
    subject = user.auth_subject
    if not _is_auth0_subject(subject):
        raise HTTPException(
            status_code=403,
            detail="Authenticated user is not managed by Auth0",
        )
    return str(subject)


def _iso_or_none(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _request_ip(request: Request) -> str | None:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",", 1)[0].strip() or None
    x_real = request.headers.get("X-Real-IP")
    if x_real:
        return x_real.strip() or None
    client = request.client
    if client and client.host:
        return str(client.host)
    return None


def _request_user_agent(request: Request) -> str | None:
    value = request.headers.get("User-Agent")
    if not value:
        return None
    text = value.strip()
    return text or None


def _request_connection(request: Request) -> str | None:
    claims = getattr(request.state, "oidc_claims", None)
    if not isinstance(claims, dict):
        return None
    for key in ("https://aqp/connection", "connection"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _request_picture(request: Request) -> str | None:
    claims = getattr(request.state, "oidc_claims", None)
    if not isinstance(claims, dict):
        return None
    value = claims.get("picture")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _load_user_snapshot(user: CurrentUser) -> dict[str, Any]:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import User

    with get_session() as session:
        row = session.query(User).filter(User.id == user.id).one_or_none()
        if row is None:
            return {
                "id": user.id,
                "email": user.email,
                "display_name": user.display_name,
                "auth_provider": user.auth_provider,
                "auth_subject": user.auth_subject,
                "avatar_url": None,
                "created_at": None,
                "last_login_at": None,
            }
        return {
            "id": row.id,
            "email": row.email,
            "display_name": row.display_name,
            "auth_provider": row.auth_provider,
            "auth_subject": row.auth_subject,
            "avatar_url": row.avatar_url,
            "created_at": row.created_at,
            "last_login_at": row.last_login_at,
        }


def _scope_counts(user: CurrentUser) -> tuple[int, int, int]:
    from aqp.auth.user import accessible_labs, accessible_projects, accessible_workspaces

    return (
        len(accessible_workspaces(user)),
        len(accessible_projects(user)),
        len(accessible_labs(user)),
    )


def _connected_accounts(payload: dict[str, Any]) -> tuple[list[ConnectedAccount], str | None]:
    identities_raw = payload.get("identities")
    if not isinstance(identities_raw, list):
        return [], None
    accounts: list[ConnectedAccount] = []
    for idx, identity in enumerate(identities_raw):
        if not isinstance(identity, dict):
            continue
        provider = str(identity.get("provider") or "").strip()
        connection = str(identity.get("connection") or "").strip()
        user_id = str(identity.get("user_id") or "").strip()
        if not provider or not connection or not user_id:
            continue
        profile_data = identity.get("profileData")
        if not isinstance(profile_data, dict):
            profile_data = {}
        accounts.append(
            ConnectedAccount(
                provider=provider,
                connection=connection,
                user_id=user_id,
                profile_data=profile_data,
                is_primary=(idx == 0),
                is_social=bool(identity.get("isSocial", False)),
            )
        )
    primary_connection = accounts[0].connection if accounts else None
    return accounts, primary_connection


def _to_me_profile(*, user: CurrentUser, request: Request) -> MeProfile:
    snapshot = _load_user_snapshot(user)
    workspace_count, project_count, lab_count = _scope_counts(user)

    picture = _request_picture(request)
    profile = MeProfile(
        id=str(snapshot["id"]),
        email=str(snapshot["email"]),
        display_name=str(snapshot["display_name"]),
        auth_provider=str(snapshot["auth_provider"]),
        auth_subject=(
            str(snapshot["auth_subject"]) if snapshot.get("auth_subject") is not None else None
        ),
        picture=picture,
        avatar_url=(
            str(snapshot["avatar_url"]) if snapshot.get("avatar_url") is not None else None
        ),
        is_default=bool(user.is_default),
        created_at=_iso_or_none(snapshot.get("created_at")),
        last_login_at=_iso_or_none(snapshot.get("last_login_at")),
        auth0_user_id=None,
        email_verified=None,
        mfa_enabled=False,
        factor_count=0,
        session_count=0,
        connection=None,
        connected_account_count=0,
        workspace_count=workspace_count,
        project_count=project_count,
        lab_count=lab_count,
    )

    auth0_user_id = user.auth_subject if _is_auth0_subject(user.auth_subject) else None
    if not auth0_user_id:
        return profile

    try:
        management = _get_management_client_or_502()
        auth0_user = _wrap_management_call(management.get_user, auth0_user_id)
        factors = _wrap_management_call(
            management.list_authentication_methods,
            auth0_user_id,
        )
        sessions = _wrap_management_call(management.list_user_sessions, auth0_user_id)
        accounts, primary_connection = _connected_accounts(auth0_user)
        email_verified_raw = auth0_user.get("email_verified")
        email_verified = (
            bool(email_verified_raw) if email_verified_raw is not None else None
        )
        profile_picture = auth0_user.get("picture")
        if isinstance(profile_picture, str) and profile_picture.strip():
            profile.picture = profile_picture.strip()
        profile.auth0_user_id = auth0_user_id
        profile.email_verified = email_verified
        profile.factor_count = len(factors)
        profile.session_count = len(sessions)
        profile.mfa_enabled = profile.factor_count > 0
        profile.connection = primary_connection
        profile.connected_account_count = len(accounts)
    except HTTPException as exc:
        logger.warning(
            "Auth0 enrichment failed for user_id=%s: %s",
            user.id,
            exc.detail,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected Auth0 enrichment failure for user_id=%s", user.id)

    return profile


def _audit_severity_from_auth0_log(event_type: str, description: str | None) -> str:
    if event_type.lower().startswith("f"):
        return "warning"
    if description and "fail" in description.lower():
        return "warning"
    return "info"


@router.get("", response_model=MeProfile)
def get_me(
    request: Request,
    user: CurrentUser = Depends(current_user),
) -> MeProfile:
    return _to_me_profile(user=user, request=request)


@router.patch("", response_model=MeProfile)
def update_me(
    body: UpdateMeRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> MeProfile:
    from aqp.auth.audit import emit_audit_event
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import User

    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return _to_me_profile(user=user, request=request)

    if "display_name" in fields and fields["display_name"] is None:
        raise HTTPException(status_code=400, detail="display_name cannot be null")

    auth0_user_id = user.auth_subject if _is_auth0_subject(user.auth_subject) else None
    if auth0_user_id:
        patch: dict[str, Any] = {}
        if "display_name" in fields:
            patch["name"] = fields["display_name"]
        if "picture" in fields:
            patch["picture"] = fields["picture"]
        if patch:
            management = _get_management_client_or_502()
            _wrap_management_call(management.update_user, auth0_user_id, patch)

    with get_session() as session:
        row = session.query(User).filter(User.id == user.id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="user not found")
        if "display_name" in fields:
            row.display_name = str(fields["display_name"])
        if "avatar_url" in fields:
            row.avatar_url = fields["avatar_url"]
        row.updated_at = datetime.utcnow()

    emit_audit_event(
        "profile_update",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="info",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"fields_changed": sorted(fields.keys())},
    )
    return _to_me_profile(user=user, request=request)


@router.post("/change-password", response_model=ChangePasswordResponse)
def create_change_password_ticket(
    body: ChangePasswordRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> ChangePasswordResponse:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    ticket = _wrap_management_call(
        management.create_password_change_ticket,
        auth0_user_id,
        return_url=body.return_url,
    )
    emit_audit_event(
        "password_change_ticket_created",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="info",
        source="api",
        connection=_request_connection(request),
        request=request,
    )
    return ChangePasswordResponse(ticket_url=ticket.ticket, expires_at=ticket.expires_at)


@router.get("/mfa/factors", response_model=list[MfaFactor])
def list_mfa_factors(
    user: CurrentUser = Depends(current_user),
) -> list[MfaFactor]:
    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    factors = _wrap_management_call(
        management.list_authentication_methods,
        auth0_user_id,
    )
    return [
        MfaFactor(
            id=factor.id,
            type=factor.type,
            name=factor.name,
            enrolled_at=factor.enrolled_at,
            confirmed=factor.confirmed,
            phone_number=factor.phone_number,
        )
        for factor in factors
    ]


@router.post("/mfa/enroll", response_model=MfaEnrollment)
def enroll_mfa(
    body: MfaEnrollRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> MfaEnrollment:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    ticket = _wrap_management_call(
        management.create_mfa_enrollment_ticket,
        auth0_user_id,
        body.factor,
        return_url=body.return_url,
    )
    emit_audit_event(
        "mfa_enroll_start",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="info",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"factor": body.factor},
    )
    return MfaEnrollment(
        ticket_id=ticket.ticket_id,
        ticket_url=ticket.ticket_url,
        qr_code_url=ticket.qr_code_url,
        secret=ticket.secret,
        recovery_codes=ticket.recovery_codes,
        expires_at=ticket.expires_at,
    )


@router.delete(
    "/mfa/factors/{factor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_mfa_factor(
    factor_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> Response:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    _wrap_management_call(
        management.delete_authentication_method,
        auth0_user_id,
        factor_id,
    )
    emit_audit_event(
        "mfa_factor_removed",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="warning",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"factor_id": factor_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[Session])
def list_sessions(
    request: Request,
    user: CurrentUser = Depends(current_user),
) -> list[Session]:
    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    sessions = _wrap_management_call(management.list_user_sessions, auth0_user_id)

    request_ip = _request_ip(request)
    request_ua = _request_user_agent(request)
    out: list[Session] = []
    for entry in sessions:
        ip_match = bool(request_ip and entry.ip and request_ip == entry.ip)
        ua_match = bool(request_ua and entry.user_agent and request_ua == entry.user_agent)
        out.append(
            Session(
                id=entry.id,
                user_id=entry.user_id,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
                last_activity=entry.last_activity,
                ip=entry.ip,
                user_agent=entry.user_agent,
                device=entry.device,
                location=entry.location,
                is_current=bool((ip_match and ua_match) or (ip_match and not request_ua)),
            )
        )
    return out


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def revoke_session(
    session_id: str,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> Response:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    sessions = _wrap_management_call(management.list_user_sessions, auth0_user_id)
    if session_id not in {entry.id for entry in sessions}:
        raise HTTPException(status_code=404, detail="session not found")
    _wrap_management_call(management.revoke_session, session_id)
    emit_audit_event(
        "session_revoke",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="warning",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"session_id": session_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions", response_model=RevokeAllSessionsResponse)
def revoke_all_sessions(
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> RevokeAllSessionsResponse:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    revoked = _wrap_management_call(
        management.revoke_all_sessions_for_user,
        auth0_user_id,
    )
    emit_audit_event(
        "session_revoke_all",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="warning",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"revoked_count": int(revoked)},
    )
    return RevokeAllSessionsResponse(revoked=int(revoked))


@router.get("/connected-accounts", response_model=list[ConnectedAccount])
def list_connected_accounts(
    user: CurrentUser = Depends(current_user),
) -> list[ConnectedAccount]:
    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    payload = _wrap_management_call(management.get_user, auth0_user_id)
    accounts, _ = _connected_accounts(payload)
    return accounts


@router.post("/connected-accounts/link", response_model=LinkAccountResponse)
def link_connected_account(
    body: LinkAccountRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> LinkAccountResponse:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    result = _wrap_management_call(
        management.link_account,
        auth0_user_id,
        secondary_jwt=body.secondary_jwt,
    )
    emit_audit_event(
        "connection_link",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="info",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"linked_to": result},
    )
    return LinkAccountResponse(link_url="/me/connected-accounts", state="linked")


@router.delete(
    "/connected-accounts/{secondary_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def unlink_connected_account(
    secondary_user_id: str,
    body: UnlinkAccountRequest,
    request: Request,
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> Response:
    from aqp.auth.audit import emit_audit_event

    auth0_user_id = _require_auth0_user_id(user)
    management = _get_management_client_or_502()
    payload = _wrap_management_call(management.get_user, auth0_user_id)
    identities = payload.get("identities")
    if not isinstance(identities, list):
        identities = []
    exists = any(
        isinstance(identity, dict)
        and str(identity.get("provider") or "").strip() == body.provider
        and str(identity.get("user_id") or "").strip() == secondary_user_id
        for identity in identities
    )
    if not exists:
        raise HTTPException(status_code=404, detail="connected account not found")
    _wrap_management_call(
        management.unlink_account,
        auth0_user_id,
        provider=body.provider,
        secondary_user_id=secondary_user_id,
    )
    emit_audit_event(
        "connection_unlink",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="warning",
        source="api",
        connection=_request_connection(request),
        request=request,
        details={"provider": body.provider, "secondary_user_id": secondary_user_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audit", response_model=AuditPage)
def get_me_audit(
    per_page: int = Query(default=50, ge=1, le=200),
    page: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(current_user),
) -> AuditPage:
    from aqp.persistence.db import get_session
    from aqp.persistence.models_audit import SecurityAuditEvent

    with get_session() as session:
        query = session.query(SecurityAuditEvent).filter(SecurityAuditEvent.user_id == user.id)
        local_total = int(query.count())
        rows = (
            query.order_by(SecurityAuditEvent.created_at.desc())
            .offset(page * per_page)
            .limit(per_page)
            .all()
        )
        # Materialise inside the session — `with get_session()` closes the
        # session on exit and any attribute access on `row` outside that
        # block raises DetachedInstanceError.
        events: list[AuditEvent] = [
            AuditEvent(
                id=row.id,
                date=_iso_or_none(row.created_at) or "",
                event_type=row.event_type,
                event_category=row.event_category,
                severity=row.severity,
                source=row.source,
                ip=row.ip,
                user_agent=row.user_agent,
                connection=row.connection,
                details=row.details if isinstance(row.details, dict) else {},
            )
            for row in rows
        ]

    warnings: list[str] = []
    seen = {(event.date, event.event_type) for event in events}
    auth0_user_id = user.auth_subject if _is_auth0_subject(user.auth_subject) else None
    if auth0_user_id:
        try:
            management = _get_management_client_or_502()
            logs = _wrap_management_call(
                management.list_user_logs,
                auth0_user_id,
                per_page=per_page,
                page=page,
            )
            for entry in logs:
                key = (entry.date, entry.type)
                if key in seen:
                    continue
                seen.add(key)
                events.append(
                    AuditEvent(
                        id=entry.log_id,
                        date=entry.date,
                        event_type=entry.type,
                        event_category="authn",
                        severity=_audit_severity_from_auth0_log(
                            entry.type,
                            entry.description,
                        ),
                        source="auth0",
                        ip=entry.ip,
                        user_agent=entry.user_agent,
                        connection=entry.connection,
                        details={
                            "description": entry.description or "",
                            "upstream": "auth0",
                        },
                    )
                )
        except HTTPException as exc:
            warnings.append(str(exc.detail))

    events.sort(key=lambda item: item.date, reverse=True)
    paged_events = events[:per_page]
    total = max(local_total, len(paged_events))
    return AuditPage(
        events=paged_events,
        total=total,
        page=page,
        per_page=per_page,
        warnings=warnings,
    )


@router.delete("", response_model=DeleteMeResponse)
def delete_me(
    request: Request,
    confirm_email: str | None = Header(default=None, alias="X-AQP-Confirm-Email"),
    user: CurrentUser = Depends(current_user),
    ctx: RequestContext = Depends(current_context),
) -> DeleteMeResponse:
    from aqp.auth.audit import emit_audit_event
    from aqp.persistence.db import get_session
    from aqp.persistence.models_tenancy import User

    if not confirm_email or confirm_email.strip().lower() != user.email.strip().lower():
        raise HTTPException(
            status_code=400,
            detail="X-AQP-Confirm-Email must match the authenticated email",
        )

    emit_audit_event(
        "account_delete",
        user_id=user.id,
        organization_id=ctx.org_id,
        workspace_id=ctx.workspace_id,
        actor_user_id=user.id,
        event_category="account",
        severity="critical",
        source="api",
        connection=_request_connection(request),
        request=request,
    )

    auth0_user_id = user.auth_subject if _is_auth0_subject(user.auth_subject) else None
    if auth0_user_id:
        try:
            management = _get_management_client_or_502()
            try:
                _wrap_management_call(
                    management.revoke_all_sessions_for_user,
                    auth0_user_id,
                )
            except HTTPException as exc:
                logger.warning(
                    "Best-effort session revoke failed for user_id=%s: %s",
                    user.id,
                    exc.detail,
                )
            try:
                _wrap_management_call(management.delete_user, auth0_user_id)
            except HTTPException as exc:
                logger.warning(
                    "Best-effort Auth0 delete failed for user_id=%s: %s",
                    user.id,
                    exc.detail,
                )
        except HTTPException as exc:
            logger.warning(
                "Auth0 management client unavailable during delete for user_id=%s: %s",
                user.id,
                exc.detail,
            )

    with get_session() as session:
        row = session.query(User).filter(User.id == user.id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="user not found")
        row.status = "deleted"
        row.email = f"deleted-{row.id}@deleted.aqp.local"
        row.display_name = "Deleted User"
        row.avatar_url = None
        row.auth_subject = None
        row.updated_at = datetime.utcnow()

    return DeleteMeResponse(status="deleted")


__all__ = ["router"]
