"""SCIM 2.0 provisioning API for Auth0 -> AQP tenancy sync.

The endpoints are intentionally narrow and map onto existing tenancy
tables:

- SCIM Users -> :class:`aqp.persistence.models_tenancy.User`
- SCIM Groups -> :class:`aqp.persistence.models_tenancy.Team`
- SCIM Group.members -> :class:`aqp.persistence.models_tenancy.Membership`

Authentication is M2M bearer-only. The verifier accepts either:

1. a JWT validated through the configured OIDC/JWKS path with audience
   ``AQP_AUTH_SCIM_M2M_AUDIENCE`` (or ``AQP_AUTH_M2M_AUDIENCE``), or
2. a static bearer token whose SHA-256 hash equals
   ``AQP_AUTH_SCIM_BEARER_TOKEN_HASH``.

The static hash path is useful for Auth0 jobs / integrations that do
not mint a JWT but can hold a long random token. Raw tokens are never
stored in settings or logs.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from aqp.auth.audit import emit_audit_event
from aqp.auth.oidc import (
    InvalidTokenError,
    JWKSUnavailableError,
    OIDCConfig,
    OIDCError,
    get_oidc_config,
    validate_jwt,
)
from aqp.config.defaults import DEFAULT_ORG_ID, ROLE_VIEWER
from aqp.persistence.db import get_session
from aqp.persistence.models_tenancy import Membership, Organization, Team, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["scim"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_PATCH_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


class ScimEmail(BaseModel):
    value: str
    primary: bool = True
    type: str = "work"


class ScimName(BaseModel):
    formatted: str | None = None
    givenName: str | None = None
    familyName: str | None = None


class ScimMember(BaseModel):
    value: str
    display: str | None = None


class ScimUserPayload(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_USER_SCHEMA])
    userName: str
    externalId: str | None = None
    name: ScimName | None = None
    displayName: str | None = None
    active: bool = True
    emails: list[ScimEmail] = Field(default_factory=list)


class ScimGroupPayload(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_GROUP_SCHEMA])
    displayName: str
    externalId: str | None = None
    members: list[ScimMember] = Field(default_factory=list)


class ScimPatchOp(BaseModel):
    op: str
    path: str | None = None
    value: Any = None


class ScimPatchPayload(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [SCIM_PATCH_SCHEMA])
    Operations: list[ScimPatchOp] = Field(default_factory=list)


def require_scim_token(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Verify SCIM bearer auth and return verified claims / metadata."""
    try:
        from aqp.config import settings
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"settings unavailable: {exc}") from exc

    if not bool(getattr(settings, "auth_scim_enabled", False)):
        raise HTTPException(status_code=404, detail="SCIM provisioning is disabled")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing SCIM Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expected_hash = str(getattr(settings, "auth_scim_bearer_token_hash", "") or "").strip()
    if expected_hash and _constant_time_equals(token_hash, expected_hash):
        return {"sub": "scim:static-token", "auth": "static_hash"}

    cfg = get_oidc_config()
    if cfg is None:
        raise HTTPException(status_code=503, detail="OIDC is not configured for SCIM")
    audience = (
        str(getattr(settings, "auth_scim_m2m_audience", "") or "").strip()
        or str(getattr(settings, "auth_m2m_audience", "") or "").strip()
        or cfg.audience
    )
    m2m_cfg = OIDCConfig(
        issuer=cfg.issuer,
        audience=audience,
        client_id=cfg.client_id,
        jwks_ttl_seconds=cfg.jwks_ttl_seconds,
        leeway_seconds=cfg.leeway_seconds,
    )
    try:
        claims = validate_jwt(token, config=m2m_cfg)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except JWKSUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OIDCError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return dict(claims)


def _constant_time_equals(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode(), strict=True):
        result |= x ^ y
    return result == 0


@router.get("/ServiceProviderConfig")
def service_provider_config(_claims: dict[str, Any] = Depends(require_scim_token)) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": 200},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer"}],
    }


@router.get("/Schemas")
def schemas(_claims: dict[str, Any] = Depends(require_scim_token)) -> dict[str, Any]:
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": 2,
        "itemsPerPage": 2,
        "startIndex": 1,
        "Resources": [
            {"id": SCIM_USER_SCHEMA, "name": "User", "attributes": []},
            {"id": SCIM_GROUP_SCHEMA, "name": "Group", "attributes": []},
        ],
    }


@router.get("/ResourceTypes")
def resource_types(_claims: dict[str, Any] = Depends(require_scim_token)) -> dict[str, Any]:
    return {
        "schemas": [SCIM_LIST_SCHEMA],
        "totalResults": 2,
        "itemsPerPage": 2,
        "startIndex": 1,
        "Resources": [
            {"id": "User", "name": "User", "endpoint": "/Users", "schema": SCIM_USER_SCHEMA},
            {"id": "Group", "name": "Group", "endpoint": "/Groups", "schema": SCIM_GROUP_SCHEMA},
        ],
    }


@router.get("/Users")
def list_users(
    filter: str | None = Query(default=None),  # noqa: A002 - SCIM field name
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        q = session.query(User)
        if filter:
            email = _extract_filter_value(filter, "userName") or _extract_filter_value(filter, "externalId")
            if email:
                q = q.filter((User.email == email.lower()) | (User.auth_subject == email))
        total = q.count()
        rows = q.order_by(User.email).offset(startIndex - 1).limit(count).all()
        return _list_response([_user_to_scim(row) for row in rows], total, startIndex, len(rows))


@router.post("/Users", status_code=201)
def create_user(
    body: ScimUserPayload,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        row = _upsert_user(session, body)
        session.flush()
        emit_audit_event(
            "scim.user.upsert",
            user_id=row.id,
            event_category="tenancy",
            source="api",
            request=request,
            details={"externalId": body.externalId, "active": body.active},
        )
        return _user_to_scim(row)


@router.get("/Users/{user_id}")
def get_user(user_id: str, _claims: dict[str, Any] = Depends(require_scim_token)) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="SCIM user not found")
        return _user_to_scim(row)


@router.put("/Users/{user_id}")
def replace_user(
    user_id: str,
    body: ScimUserPayload,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="SCIM user not found")
        _apply_user_payload(row, body)
        row.updated_at = datetime.utcnow()
        session.flush()
        emit_audit_event("scim.user.replace", user_id=row.id, event_category="tenancy", source="api", request=request)
        return _user_to_scim(row)


@router.patch("/Users/{user_id}")
def patch_user(
    user_id: str,
    body: ScimPatchPayload,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(User, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="SCIM user not found")
        for op in body.Operations:
            if (op.path or "").lower() == "active":
                row.status = "active" if bool(op.value) else "disabled"
        row.updated_at = datetime.utcnow()
        session.flush()
        emit_audit_event("scim.user.patch", user_id=row.id, event_category="tenancy", source="api", request=request)
        return _user_to_scim(row)


@router.delete(
    "/Users/{user_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
def delete_user(
    user_id: str,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> None:
    with get_session() as session:
        row = session.get(User, user_id)
        if row is None:
            return None
        row.status = "disabled"
        row.updated_at = datetime.utcnow()
        session.flush()
        emit_audit_event("scim.user.deactivate", user_id=row.id, event_category="tenancy", source="api", request=request)
    return None


@router.get("/Groups")
def list_groups(
    filter: str | None = Query(default=None),  # noqa: A002
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=200),
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        q = session.query(Team)
        if filter:
            name = _extract_filter_value(filter, "displayName") or _extract_filter_value(filter, "externalId")
            if name:
                q = q.filter((Team.name == name) | (Team.slug == _slugify(name)))
        total = q.count()
        rows = q.order_by(Team.name).offset(startIndex - 1).limit(count).all()
        return _list_response([_group_to_scim(session, row) for row in rows], total, startIndex, len(rows))


@router.post("/Groups", status_code=201)
def create_group(
    body: ScimGroupPayload,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        org = _default_org(session)
        row = (
            session.query(Team)
            .filter(Team.org_id == org.id)
            .filter(Team.slug == _slugify(body.externalId or body.displayName))
            .one_or_none()
        )
        if row is None:
            row = Team(org_id=org.id, slug=_slugify(body.externalId or body.displayName), name=body.displayName)
            session.add(row)
        row.name = body.displayName
        row.meta = {**(row.meta or {}), "scim": {"externalId": body.externalId}}
        session.flush()
        _sync_group_members(session, row, body.members)
        emit_audit_event("scim.group.upsert", organization_id=org.id, event_category="tenancy", source="api", request=request, details={"team_id": row.id})
        return _group_to_scim(session, row)


@router.get("/Groups/{group_id}")
def get_group(group_id: str, _claims: dict[str, Any] = Depends(require_scim_token)) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(Team, group_id)
        if row is None:
            raise HTTPException(status_code=404, detail="SCIM group not found")
        return _group_to_scim(session, row)


@router.patch("/Groups/{group_id}")
def patch_group(
    group_id: str,
    body: ScimPatchPayload,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> dict[str, Any]:
    with get_session() as session:
        row = session.get(Team, group_id)
        if row is None:
            raise HTTPException(status_code=404, detail="SCIM group not found")
        for op in body.Operations:
            path = (op.path or "").lower()
            if path == "members" or path.startswith("members"):
                members = [ScimMember.model_validate(x) for x in (op.value or [])]
                _sync_group_members(session, row, members)
            elif path == "displayname":
                row.name = str(op.value)
        session.flush()
        emit_audit_event("scim.group.patch", organization_id=row.org_id, event_category="tenancy", source="api", request=request, details={"team_id": row.id})
        return _group_to_scim(session, row)


@router.delete(
    "/Groups/{group_id}",
    status_code=204,
    response_class=Response,
    response_model=None,
)
def delete_group(
    group_id: str,
    request: Request,
    _claims: dict[str, Any] = Depends(require_scim_token),
) -> None:
    with get_session() as session:
        row = session.get(Team, group_id)
        if row is not None:
            row.meta = {**(row.meta or {}), "scim_deleted": True}
            session.flush()
            emit_audit_event("scim.group.delete", organization_id=row.org_id, event_category="tenancy", source="api", request=request, details={"team_id": row.id})
    return None


def _list_response(resources: list[dict[str, Any]], total: int, start: int, count: int) -> dict[str, Any]:
    return {"schemas": [SCIM_LIST_SCHEMA], "totalResults": total, "startIndex": start, "itemsPerPage": count, "Resources": resources}


def _user_to_scim(row: User) -> dict[str, Any]:
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": row.id,
        "externalId": (row.meta or {}).get("scim", {}).get("externalId"),
        "userName": row.email,
        "displayName": row.display_name,
        "active": row.status == "active",
        "emails": [{"value": row.email, "primary": True, "type": "work"}],
        "meta": {"resourceType": "User", "created": row.created_at.isoformat(), "lastModified": row.updated_at.isoformat()},
    }


def _group_to_scim(session: Any, row: Team) -> dict[str, Any]:
    memberships = (
        session.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.scope_kind == "team")
        .filter(Membership.scope_id == row.id)
        .all()
    )
    return {
        "schemas": [SCIM_GROUP_SCHEMA],
        "id": row.id,
        "externalId": (row.meta or {}).get("scim", {}).get("externalId"),
        "displayName": row.name,
        "members": [{"value": user.id, "display": user.display_name} for _membership, user in memberships],
        "meta": {"resourceType": "Group", "created": row.created_at.isoformat(), "lastModified": row.updated_at.isoformat()},
    }


def _upsert_user(session: Any, body: ScimUserPayload) -> User:
    email = _primary_email(body) or body.userName
    email = email.lower()
    row = session.query(User).filter(User.email == email).one_or_none()
    if row is None and body.externalId:
        row = session.query(User).filter(User.auth_subject == body.externalId).one_or_none()
    if row is None:
        row = User(email=email, display_name=body.displayName or email, auth_provider="auth0", auth_subject=body.externalId or body.userName)
        session.add(row)
    _apply_user_payload(row, body)
    return row


def _apply_user_payload(row: User, body: ScimUserPayload) -> None:
    email = _primary_email(body) or body.userName
    row.email = email.lower()
    row.display_name = body.displayName or (body.name.formatted if body.name else None) or row.email
    row.auth_provider = "auth0"
    row.auth_subject = body.externalId or body.userName
    row.status = "active" if body.active else "disabled"
    row.meta = {**(row.meta or {}), "scim": {"externalId": body.externalId, "userName": body.userName}}
    row.updated_at = datetime.utcnow()


def _primary_email(body: ScimUserPayload) -> str | None:
    for email in body.emails:
        if email.primary and email.value:
            return email.value
    return body.emails[0].value if body.emails else None


def _default_org(session: Any) -> Organization:
    row = session.get(Organization, DEFAULT_ORG_ID)
    if row is not None:
        return row
    row = session.query(Organization).order_by(Organization.created_at.asc()).first()
    if row is None:
        row = Organization(id=DEFAULT_ORG_ID, slug="wiley-tech", name="Wiley Tech")
        session.add(row)
        session.flush()
    return row


def _sync_group_members(session: Any, team: Team, members: list[ScimMember]) -> None:
    desired_ids = {m.value for m in members if m.value}
    existing = (
        session.query(Membership)
        .filter(Membership.scope_kind == "team")
        .filter(Membership.scope_id == team.id)
        .all()
    )
    for membership in existing:
        if membership.user_id not in desired_ids:
            session.delete(membership)
    existing_ids = {m.user_id for m in existing}
    for user_id in desired_ids - existing_ids:
        if session.get(User, user_id) is None:
            continue
        session.add(Membership(user_id=user_id, scope_kind="team", scope_id=team.id, role=ROLE_VIEWER, meta={"source": "scim"}))


def _extract_filter_value(raw: str, field: str) -> str | None:
    prefix = f'{field} eq "'
    if raw.startswith(prefix) and raw.endswith('"'):
        return raw[len(prefix):-1]
    return None


def _slugify(value: str) -> str:
    import re

    text = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return text or "scim-group"


__all__ = ["router", "require_scim_token"]
