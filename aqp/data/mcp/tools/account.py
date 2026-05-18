"""Read-only account DataMCP tools.

These tools expose the authenticated actor's account state (whoami,
sessions, MFA factors, audit events, invites, linked identities) to
agents without bypassing AGENTS rule 22.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from aqp.auth.management_api import Auth0ManagementError, get_management_client
from aqp.data.mcp.base import DataMCPTool, MCPPolicyError, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session, enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _require_actor(ctx: MCPToolContext) -> str:
    actor = str(ctx.actor or "").strip()
    if not actor:
        raise MCPPolicyError("ctx.actor is required for account tools")
    return actor


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _scope_refs(user: Any, ids: list[str], *, scope_kind: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for scope_id in ids:
        role = user.role_for(scope_kind, scope_id) if hasattr(user, "role_for") else None
        live_control = any(
            bool(m.get("live_control"))
            for m in list(getattr(user, "memberships", []) or [])
            if m.get("scope_kind") == scope_kind and m.get("scope_id") == scope_id
        )
        refs.append({"id": scope_id, "role": role, "live_control": live_control})
    return refs


def _first_scope_id(
    memberships: list[dict[str, Any]],
    *,
    scope_kind: str,
) -> str | None:
    candidates = [
        str(m.get("scope_id", "")).strip()
        for m in memberships
        if str(m.get("scope_kind", "")).strip() == scope_kind
        and str(m.get("scope_id", "")).strip()
    ]
    if not candidates:
        return None
    return sorted(candidates)[0]


def _is_auth0_subject(subject: str | None) -> bool:
    return bool(subject and "|" in subject)


def _serialize_session(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_activity": row.last_activity,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "device": row.device,
        "location": row.location,
    }


def _serialize_factor(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "name": row.name,
        "enrolled_at": row.enrolled_at,
        "confirmed": bool(row.confirmed),
        "phone_number": row.phone_number,
    }


def _split_subject(subject: str) -> tuple[str, str]:
    provider, _, user_id = subject.partition("|")
    return provider, user_id


def _serialize_identity(
    row: dict[str, Any],
    *,
    primary_provider: str,
    primary_user_id: str,
) -> dict[str, Any]:
    provider = str(row.get("provider") or "")
    user_id = str(row.get("user_id") or "")
    profile_data = row.get("profileData")
    if not isinstance(profile_data, dict):
        profile_data = row.get("profile_data")
    if not isinstance(profile_data, dict):
        profile_data = {}
    return {
        "provider": provider,
        "connection": str(row.get("connection") or ""),
        "user_id": user_id,
        "profile_data": profile_data,
        "is_primary": provider == primary_provider and user_id == primary_user_id,
    }


def _serialize_audit_event(row: Any) -> dict[str, Any]:
    details = row.details if isinstance(row.details, dict) else {}
    return {
        "id": row.id,
        "date": _iso(row.created_at),
        "event_type": row.event_type,
        "event_category": row.event_category,
        "severity": row.severity,
        "source": row.source,
        "ip": row.ip,
        "user_agent": row.user_agent,
        "connection": row.connection,
        "details": details,
    }


def _serialize_invite(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "organization_id": row.organization_id,
        "workspace_id": row.workspace_id,
        "team_id": row.team_id,
        "email": row.email,
        "role": row.role,
        "invited_by_user_id": row.invited_by_user_id,
        "token_prefix": (str(row.token_prefix or "")[:8] or None),
        "status": row.status,
        "message": row.message,
        "expires_at": _iso(row.expires_at),
        "accepted_at": _iso(row.accepted_at),
        "accepted_by_user_id": row.accepted_by_user_id,
        "revoked_at": _iso(row.revoked_at),
        "revoked_by_user_id": row.revoked_by_user_id,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class _AccountReadOnlyTool(DataMCPTool):
    """Common policy checks for account read-only tools."""

    mutates: ClassVar[bool] = False
    required_scopes: ClassVar[tuple[str, ...]] = ("data:read",)

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=self.mutates)
        if ctx.actor_kind and ctx.actor_kind != "user":
            raise MCPPolicyError("account tools require actor_kind='user'")
        _require_actor(ctx)


class _TenancyScopedAccountReadOnlyTool(_AccountReadOnlyTool):
    """Adds strict tenant-context checks for tenant-scoped account reads."""

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=True)


class WhoAmIInput(BaseModel):
    """Empty input — the actor is always derived from the MCPToolContext."""

    pass


@register_data_mcp_tool
class AccountWhoAmITool(_AccountReadOnlyTool):
    name = "data.account.whoami"
    description = (
        "Return the current actor's resolved identity: email, display "
        "name, provider, auth_subject, and tenancy summary (active "
        "org / workspace / project / lab + memberships). Read-only "
        "mirror of GET /auth/whoami suitable for agent prompts. "
        "Use this before invoking any /me/* mutation tool."
    )
    args_schema = WhoAmIInput
    category = "account"
    tags = ("account", "identity", "tenancy")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
    ) -> MCPToolResult:
        from aqp.auth.user import (
            accessible_labs,
            accessible_projects,
            accessible_workspaces,
            resolve_user,
        )
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import User

        actor_id = _require_actor(ctx)
        user = resolve_user(user_id=actor_id)
        memberships = sorted(
            (dict(m) for m in list(user.memberships or [])),
            key=lambda m: (
                str(m.get("scope_kind", "")),
                str(m.get("scope_id", "")),
                str(m.get("role", "")),
            ),
        )
        with get_session() as session:
            row = session.query(User).filter(User.id == actor_id).one_or_none()
            avatar_url = str(row.avatar_url or "").strip() if row is not None else ""
        data = {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "auth_provider": user.auth_provider,
            "auth_subject": user.auth_subject,
            "is_default": bool(user.is_default),
            "avatar_url": avatar_url or None,
            "workspaces": _scope_refs(
                user, accessible_workspaces(user), scope_kind="workspace"
            ),
            "projects": _scope_refs(
                user, accessible_projects(user), scope_kind="project"
            ),
            "labs": _scope_refs(user, accessible_labs(user), scope_kind="lab"),
            "memberships": memberships,
            "active_context": {
                "user_id": user.id,
                "org_id": (
                    ctx.extras.get("org_id") if isinstance(ctx.extras, dict) else None
                )
                or _first_scope_id(memberships, scope_kind="org"),
                "team_id": (
                    ctx.extras.get("team_id") if isinstance(ctx.extras, dict) else None
                )
                or _first_scope_id(memberships, scope_kind="team"),
                "workspace_id": ctx.workspace_id
                or _first_scope_id(memberships, scope_kind="workspace"),
                "project_id": ctx.project_id
                or _first_scope_id(memberships, scope_kind="project"),
                "lab_id": (
                    ctx.extras.get("lab_id") if isinstance(ctx.extras, dict) else None
                )
                or _first_scope_id(memberships, scope_kind="lab"),
                "run_id": ctx.extras.get("run_id") if isinstance(ctx.extras, dict) else None,
                "experiment_id": (
                    ctx.extras.get("experiment_id") if isinstance(ctx.extras, dict) else None
                ),
                "test_id": ctx.extras.get("test_id") if isinstance(ctx.extras, dict) else None,
                "role": ctx.extras.get("role") if isinstance(ctx.extras, dict) else None,
                "live_control": bool(
                    ctx.extras.get("live_control") if isinstance(ctx.extras, dict) else False
                ),
                "extras": dict(ctx.extras or {}),
            },
        }
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=1,
            summary=f"resolved account identity for {user.email}",
        )


class ListSessionsInput(BaseModel):
    pass


@register_data_mcp_tool
class AccountListSessionsTool(_AccountReadOnlyTool):
    name = "data.account.list_sessions"
    description = (
        "List the current actor's active Auth0 sessions: id, device, "
        "IP, location, last_activity, created_at. Read-only. Returns "
        "an empty list with a warning when the user is not on Auth0 "
        "or the Management API is unreachable."
    )
    args_schema = ListSessionsInput
    category = "account"
    tags = ("account", "sessions")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import User

        actor_id = _require_actor(ctx)
        with get_session() as session:
            row = session.query(User).filter(User.id == actor_id).one_or_none()
            auth_subject = str(row.auth_subject or "").strip() if row is not None else ""
        if not _is_auth0_subject(auth_subject):
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[
                    "actor is not on Auth0 — no Management API sessions available",
                ],
                summary="no Auth0 sessions for actor",
            )
        try:
            sessions = get_management_client().list_user_sessions(auth_subject)
        except Auth0ManagementError as exc:
            logger.debug("Auth0 session lookup failed for actor=%s: %s", actor_id, exc)
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[f"Auth0 Management API unreachable: {exc}"],
                summary="Auth0 sessions unavailable",
            )
        items = [_serialize_session(row) for row in sessions]
        return MCPToolResult(
            ok=True,
            data=items,
            rows_returned=len(items),
            summary=f"listed {len(items)} active sessions",
        )


class ListFactorsInput(BaseModel):
    pass


@register_data_mcp_tool
class AccountListFactorsTool(_AccountReadOnlyTool):
    name = "data.account.list_factors"
    description = (
        "List the current actor's enrolled MFA factors (TOTP, SMS, "
        "WebAuthn, recovery codes). Used by agents that need to know "
        "if the user has step-up auth available before triggering a "
        "sensitive operation."
    )
    args_schema = ListFactorsInput
    category = "account"
    tags = ("account", "mfa")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import User

        actor_id = _require_actor(ctx)
        with get_session() as session:
            row = session.query(User).filter(User.id == actor_id).one_or_none()
            auth_subject = str(row.auth_subject or "").strip() if row is not None else ""
        if not _is_auth0_subject(auth_subject):
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[
                    "actor is not on Auth0 — no Management API factors available",
                ],
                summary="no Auth0 factors for actor",
            )
        try:
            factors = get_management_client().list_authentication_methods(auth_subject)
        except Auth0ManagementError as exc:
            logger.debug("Auth0 factor lookup failed for actor=%s: %s", actor_id, exc)
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[f"Auth0 Management API unreachable: {exc}"],
                summary="Auth0 factors unavailable",
            )
        items = [_serialize_factor(row) for row in factors]
        return MCPToolResult(
            ok=True,
            data=items,
            rows_returned=len(items),
            summary=f"listed {len(items)} MFA factors",
        )


class ListAuditEventsInput(BaseModel):
    per_page: int = Field(default=50, ge=1, le=200)
    page: int = Field(default=0, ge=0)
    event_category: Literal["authn", "authz", "account", "tenancy", "safety"] | None = None
    event_type: str | None = None
    since: datetime | None = None
    until: datetime | None = None


@register_data_mcp_tool
class AccountListAuditEventsTool(_TenancyScopedAccountReadOnlyTool):
    name = "data.account.list_audit_events"
    description = (
        "List the current actor's security audit events from local persistence. "
        "Supports category/type/time-window filters with pagination."
    )
    args_schema = ListAuditEventsInput
    category = "account"
    tags = ("account", "audit", "security")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        per_page: int = 50,
        page: int = 0,
        event_category: Literal["authn", "authz", "account", "tenancy", "safety"] | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_audit import SecurityAuditEvent

        actor_id = _require_actor(ctx)
        with get_session() as session:
            query = session.query(SecurityAuditEvent).filter(
                SecurityAuditEvent.user_id == actor_id
            )
            if event_category:
                query = query.filter(SecurityAuditEvent.event_category == event_category)
            if event_type:
                query = query.filter(SecurityAuditEvent.event_type == event_type)
            if since is not None:
                query = query.filter(SecurityAuditEvent.created_at >= since)
            if until is not None:
                query = query.filter(SecurityAuditEvent.created_at <= until)
            total = query.count()
            rows = (
                query.order_by(SecurityAuditEvent.created_at.desc())
                .offset(int(page) * int(per_page))
                .limit(int(per_page))
                .all()
            )
            # Materialise inside the session: `with get_session()` closes
            # on exit and `row.<attr>` after that raises DetachedInstanceError.
            events = [_serialize_audit_event(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=events,
            rows_returned=len(events),
            summary=f"listed {len(events)} audit events",
            metadata={"total": total, "page": int(page), "per_page": int(per_page)},
        )


class ListInvitesInput(BaseModel):
    organization_id: str = Field(
        description="Org to list invites for; the caller must administer this org."
    )
    status: Literal["pending", "claimed", "accepted", "revoked", "expired"] | None = None
    per_page: int = Field(default=50, ge=1, le=200)
    page: int = Field(default=0, ge=0)


@register_data_mcp_tool
class AccountListInvitesTool(_TenancyScopedAccountReadOnlyTool):
    name = "data.account.list_invites"
    description = (
        "List tenancy invites for an organization when the actor is an org admin. "
        "Returns token_prefix only; never returns token_hash."
    )
    args_schema = ListInvitesInput
    category = "account"
    tags = ("account", "invites", "tenancy")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
        organization_id: str,
        status: Literal["pending", "claimed", "accepted", "revoked", "expired"] | None = None,
        per_page: int = 50,
        page: int = 0,
    ) -> MCPToolResult:
        from aqp.auth.user import resolve_user, user_can
        from aqp.persistence.db import get_session
        from aqp.persistence.models_audit import TenancyInvite

        actor_id = _require_actor(ctx)
        try:
            actor_user = resolve_user(user_id=actor_id, fallback_to_default=False)
        except LookupError as exc:
            raise MCPPolicyError(f"actor {actor_id!r} could not be resolved") from exc
        if not user_can(
            actor_user,
            "admin",
            scope_kind="org",
            scope_id=organization_id,
        ):
            raise MCPPolicyError(
                f"actor {actor_id!r} is not an admin of organization {organization_id!r}"
            )
        with get_session() as session:
            query = session.query(TenancyInvite).filter(
                TenancyInvite.organization_id == organization_id
            )
            if status:
                query = query.filter(TenancyInvite.status == status)
            total = query.count()
            rows = (
                query.order_by(TenancyInvite.created_at.desc())
                .offset(int(page) * int(per_page))
                .limit(int(per_page))
                .all()
            )
            # Materialise inside the session: `with get_session()` closes
            # on exit and `row.<attr>` after that raises DetachedInstanceError.
            items = [_serialize_invite(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=items,
            rows_returned=len(items),
            summary=f"listed {len(items)} invites for organization {organization_id}",
            metadata={"total": total, "page": int(page), "per_page": int(per_page)},
        )


class ListConnectionsInput(BaseModel):
    pass


@register_data_mcp_tool
class AccountListConnectionsTool(_AccountReadOnlyTool):
    name = "data.account.list_connections"
    description = (
        "List the actor's linked Auth0 identities (Google, Microsoft, GitHub, etc.)."
    )
    args_schema = ListConnectionsInput
    category = "account"
    tags = ("account", "identity", "connections")
    mutates: ClassVar[bool] = False

    def run(
        self,
        *,
        ctx: MCPToolContext,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import User

        actor_id = _require_actor(ctx)
        with get_session() as session:
            row = session.query(User).filter(User.id == actor_id).one_or_none()
            auth_subject = str(row.auth_subject or "").strip() if row is not None else ""
        if not _is_auth0_subject(auth_subject):
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[
                    "actor is not on Auth0 — no Management API linked identities available",
                ],
                summary="no Auth0 linked identities for actor",
            )
        primary_provider, primary_user_id = _split_subject(auth_subject)
        try:
            payload = get_management_client().get_user(auth_subject)
        except Auth0ManagementError as exc:
            logger.debug("Auth0 identity lookup failed for actor=%s: %s", actor_id, exc)
            return MCPToolResult(
                ok=True,
                data=[],
                rows_returned=0,
                warnings=[f"Auth0 Management API unreachable: {exc}"],
                summary="Auth0 linked identities unavailable",
            )
        raw_identities = payload.get("identities", []) if isinstance(payload, dict) else []
        items: list[dict[str, Any]] = []
        if isinstance(raw_identities, list):
            for row in raw_identities:
                if not isinstance(row, dict):
                    continue
                items.append(
                    _serialize_identity(
                        row,
                        primary_provider=primary_provider,
                        primary_user_id=primary_user_id,
                    )
                )
        return MCPToolResult(
            ok=True,
            data=items,
            rows_returned=len(items),
            summary=f"listed {len(items)} linked identities",
        )


__all__ = [
    "AccountListAuditEventsTool",
    "AccountListConnectionsTool",
    "AccountListFactorsTool",
    "AccountListInvitesTool",
    "AccountListSessionsTool",
    "AccountWhoAmITool",
]
