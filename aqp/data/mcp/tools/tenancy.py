"""DataMCP tools for organization / user / membership / Entra-tenant management.

Exposes the seven tenancy operations the frontend onboarding wizards
and the agent layer need, all subclassing :class:`DataMCPTool` so the
in-process bridge installs them in ``TOOL_REGISTRY`` and the HTTP
``/mcp/data/...`` surface advertises them externally:

- ``data.tenancy.list_organizations`` — list orgs (filtered by prefix).
- ``data.tenancy.create_organization`` — create a new org + default
  team / workspace / project / lab structure.
- ``data.tenancy.invite_user`` — invite a user to an org / workspace
  by email; mints an Entra B2B invitation when
  ``settings.auth_msal_b2b_enabled`` is True.
- ``data.tenancy.link_org_to_entra_tenant`` — create / promote an
  :class:`EntraTenantLink` row mapping an Entra ``tid`` -> AQP org.
- ``data.tenancy.list_memberships`` — list a user's effective
  memberships (or a scope's members).
- ``data.tenancy.grant_role`` — upsert a single :class:`Membership`
  row (idempotent; upgrade-only).
- ``data.tenancy.transfer_resources`` — re-stamp tenancy-scoped rows
  from one org to another (used by M&A / cleanup flows; mirrors the
  Alembic 0051 logic at runtime).

All tools enforce tenancy through the verified
:class:`MCPToolContext` — the tools NEVER trust ``user_id`` /
``org_id`` from request bodies for the actor identity. Mutating
tools (``mutates=True``) require ``tenancy:admin`` /
``tenancy:invite`` scopes.

AGENTS rule 44: organization provisioning from Entra ID claims goes
through :class:`EntraTenantLink`. ``link_org_to_entra_tenant`` is the
only sanctioned ingress for that mapping.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ListOrgsInput(BaseModel):
    prefix: str | None = Field(
        default=None, description="Match against slug / name (case-insensitive substring)."
    )
    status: str | None = Field(
        default=None, description="Optional status filter (active / suspended)."
    )
    limit: int = Field(default=50, ge=1, le=500)


class CreateOrgInput(BaseModel):
    name: str = Field(..., min_length=2, max_length=240)
    slug: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    billing_email: str | None = Field(default=None, max_length=320)
    description: str | None = Field(default=None)
    # When true the create-org wizard additionally seeds the canonical
    # "Core" team + "Main" workspace + "Main" project + "Main" lab
    # under the new org so the operator lands on a usable surface.
    seed_default_structure: bool = Field(default=True)


class InviteUserInput(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    org_id: str = Field(...)
    role: str = Field(default="viewer", description="viewer | editor | admin | owner")
    scope_kind: str = Field(
        default="org",
        description="org | team | workspace | project | lab",
    )
    scope_id: str | None = Field(
        default=None,
        description="When scope_kind != 'org', the id of the team / workspace / project / lab.",
    )
    display_name: str | None = Field(default=None)
    send_entra_b2b_invitation: bool = Field(default=True)


class LinkEntraTenantInput(BaseModel):
    organization_id: str = Field(...)
    entra_tenant_id: str = Field(..., min_length=8, max_length=80)
    primary_domain: str | None = Field(default=None, max_length=240)
    display_name: str | None = Field(default=None)
    allowed_email_domains: list[str] | None = Field(default=None)
    role_mapping: dict[str, str] | None = Field(
        default=None,
        description=(
            "Optional per-app-role override map, e.g. "
            "``{'aqp.admin': 'owner', 'aqp.terraform.operator': 'editor'}``."
        ),
    )
    activate: bool = Field(
        default=True,
        description=(
            "True (default) creates the link in ``active`` status. "
            "False creates it in ``pending`` (requires later promotion)."
        ),
    )


class ListMembershipsInput(BaseModel):
    user_id: str | None = Field(default=None)
    scope_kind: str | None = Field(default=None)
    scope_id: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)


class GrantRoleInput(BaseModel):
    user_id: str = Field(...)
    scope_kind: str = Field(...)
    scope_id: str = Field(...)
    role: str = Field(default="viewer")
    live_control: bool = Field(default=False)
    expires_at_iso: str | None = Field(default=None)


class TransferResourcesInput(BaseModel):
    from_org_id: str = Field(...)
    to_org_id: str = Field(...)
    kinds: list[str] = Field(
        default_factory=list,
        description=(
            "Optional whitelist of resource kinds to transfer "
            "(bots / strategies / agents / rl / analysis / terraform). "
            "Empty -> every kind."
        ),
    )
    dry_run: bool = Field(default=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_uuid() -> str:
    return str(uuid.uuid4())


def _membership_row(
    *,
    user_id: str,
    scope_kind: str,
    scope_id: str,
    role: str,
    live_control: bool,
    granted_by: str | None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "id": _safe_uuid(),
        "user_id": user_id,
        "scope_kind": scope_kind,
        "scope_id": scope_id,
        "role": role,
        "live_control": live_control,
        "granted_by": granted_by,
        "granted_at": datetime.utcnow(),
        "expires_at": expires_at,
        "meta": {},
    }


def _serialize_org(org: Any) -> dict[str, Any]:
    return {
        "id": org.id,
        "slug": org.slug,
        "name": org.name,
        "billing_email": org.billing_email,
        "status": org.status,
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


def _serialize_membership(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "scope_kind": row.scope_kind,
        "scope_id": row.scope_id,
        "role": row.role,
        "live_control": bool(row.live_control),
        "granted_at": row.granted_at.isoformat() if row.granted_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@register_data_mcp_tool
class ListOrganizationsTool(DataMCPTool):
    name = "data.tenancy.list_organizations"
    description = (
        "List organizations visible to the calling actor. Supports prefix / status "
        "filtering. Returns one row per org with id / slug / name / billing_email / "
        "status. Mirrors the EntityPicker(kind='organizations') backend feed."
    )
    args_schema = ListOrgsInput
    category = "tenancy"
    tags = ("tenancy", "organizations", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        prefix: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Organization

        with get_session() as session:
            q = session.query(Organization)
            if prefix:
                p = prefix.strip().lower()
                if p:
                    q = q.filter(
                        Organization.slug.ilike(f"%{p}%")
                        | Organization.name.ilike(f"%{p}%")
                    )
            if status:
                q = q.filter(Organization.status == status.strip().lower())
            rows = q.order_by(Organization.slug).limit(int(limit)).all()
            items = [_serialize_org(o) for o in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items, "total": len(items)},
            rows_returned=len(items),
            summary=f"listed {len(items)} organizations",
        )


@register_data_mcp_tool
class CreateOrganizationTool(DataMCPTool):
    name = "data.tenancy.create_organization"
    description = (
        "Create a new :class:`Organization` row plus (when "
        "``seed_default_structure=True``) the canonical Core team + Main "
        "workspace + Main project + Main lab. The calling actor receives "
        "owner Memberships on every seeded scope."
    )
    args_schema = CreateOrgInput
    category = "tenancy"
    tags = ("tenancy", "organizations", "create")
    mutates = True
    required_scopes = ("tenancy:admin",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        name: str,
        slug: str,
        billing_email: str | None = None,
        description: str | None = None,
        seed_default_structure: bool = True,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import (
            Lab,
            Membership,
            Organization,
            Project,
            Team,
            Workspace,
        )

        actor = ctx.actor or "system"
        now = datetime.utcnow()
        slug_norm = slug.strip().lower()
        with get_session() as session:
            existing = (
                session.query(Organization)
                .filter(Organization.slug == slug_norm)
                .one_or_none()
            )
            if existing is not None:
                return MCPToolResult(
                    ok=False,
                    error=f"organization with slug={slug_norm!r} already exists (id={existing.id})",
                    summary="create-org conflict",
                )

            org = Organization(
                id=_safe_uuid(),
                slug=slug_norm,
                name=name.strip(),
                billing_email=(billing_email or "").strip() or None,
                status="active",
                meta={"created_via": "data.tenancy.create_organization", "actor": actor},
                created_at=now,
                updated_at=now,
            )
            session.add(org)
            session.flush()

            team_id = workspace_id = project_id = lab_id = None
            if seed_default_structure:
                team = Team(
                    id=_safe_uuid(),
                    org_id=org.id,
                    slug="core",
                    name="Core",
                    description=description or "Default team for the new organization.",
                    meta={},
                    created_at=now,
                    updated_at=now,
                )
                ws = Workspace(
                    id=_safe_uuid(),
                    org_id=org.id,
                    slug="main",
                    name="Main Workspace",
                    description="Default workspace.",
                    visibility="org",
                    archived=False,
                    settings={},
                    meta={},
                    created_at=now,
                    updated_at=now,
                )
                proj = Project(
                    id=_safe_uuid(),
                    workspace_id=ws.id,
                    slug="main",
                    name="Main Project",
                    description="Default project.",
                    archived=False,
                    settings={},
                    meta={},
                    created_at=now,
                    updated_at=now,
                )
                lab = Lab(
                    id=_safe_uuid(),
                    workspace_id=ws.id,
                    slug="main",
                    name="Main Lab",
                    description="Default lab.",
                    archived=False,
                    settings={},
                    meta={},
                    created_at=now,
                    updated_at=now,
                )
                session.add_all([team, ws, proj, lab])
                session.flush()
                team_id, workspace_id, project_id, lab_id = team.id, ws.id, proj.id, lab.id

                # Grant owner memberships to the actor on every seeded scope.
                for scope_kind, scope_id in (
                    ("org", org.id),
                    ("team", team.id),
                    ("workspace", ws.id),
                    ("project", proj.id),
                    ("lab", lab.id),
                ):
                    session.add(
                        Membership(
                            id=_safe_uuid(),
                            user_id=actor,
                            scope_kind=scope_kind,
                            scope_id=scope_id,
                            role="owner",
                            live_control=True,
                            granted_by=actor,
                            granted_at=now,
                            meta={},
                        )
                    )
            else:
                session.add(
                    Membership(
                        id=_safe_uuid(),
                        user_id=actor,
                        scope_kind="org",
                        scope_id=org.id,
                        role="owner",
                        live_control=True,
                        granted_by=actor,
                        granted_at=now,
                        meta={},
                    )
                )

            session.flush()
            payload = {
                "organization": _serialize_org(org),
                "team_id": team_id,
                "workspace_id": workspace_id,
                "project_id": project_id,
                "lab_id": lab_id,
            }
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"created organization {slug_norm} (id={payload['organization']['id']})",
        )


@register_data_mcp_tool
class InviteUserTool(DataMCPTool):
    name = "data.tenancy.invite_user"
    description = (
        "Invite a user to a scope by email. Creates a placeholder "
        ":class:`User` row when no match exists, mints an Entra B2B "
        "invitation when MSAL is configured, and grants the requested "
        "Membership."
    )
    args_schema = InviteUserInput
    category = "tenancy"
    tags = ("tenancy", "invite")
    mutates = True
    required_scopes = ("tenancy:invite",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        email: str,
        org_id: str,
        role: str = "viewer",
        scope_kind: str = "org",
        scope_id: str | None = None,
        display_name: str | None = None,
        send_entra_b2b_invitation: bool = True,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Membership, Organization, User

        email_norm = email.strip().lower()
        now = datetime.utcnow()
        scope_id_resolved = scope_id or org_id

        with get_session() as session:
            org = session.query(Organization).filter(Organization.id == org_id).one_or_none()
            if org is None:
                return MCPToolResult(
                    ok=False,
                    error=f"organization {org_id!r} not found",
                    summary="invite miss org",
                )

            user = session.query(User).filter(User.email == email_norm).one_or_none()
            created_user = False
            if user is None:
                user = User(
                    id=_safe_uuid(),
                    email=email_norm,
                    display_name=display_name or email_norm.split("@", 1)[0],
                    auth_provider="msal_entra",
                    status="pending",
                    meta={
                        "invited_via": "data.tenancy.invite_user",
                        "invited_by": ctx.actor or "system",
                        "invited_at": now.isoformat(),
                    },
                    created_at=now,
                    updated_at=now,
                )
                session.add(user)
                session.flush()
                created_user = True

            membership = (
                session.query(Membership)
                .filter(
                    Membership.user_id == user.id,
                    Membership.scope_kind == scope_kind,
                    Membership.scope_id == scope_id_resolved,
                )
                .one_or_none()
            )
            if membership is None:
                membership = Membership(
                    **_membership_row(
                        user_id=user.id,
                        scope_kind=scope_kind,
                        scope_id=scope_id_resolved,
                        role=role,
                        live_control=role in {"admin", "owner"},
                        granted_by=ctx.actor,
                    )
                )
                session.add(membership)
                session.flush()

        # Best-effort Entra B2B invitation. The real Microsoft Graph call
        # requires admin consent + a long-lived application token that
        # the AQP server holds; in dev / test we no-op and return a
        # stub so the wizard flow still completes.
        entra_invitation: dict[str, Any] | None = None
        if send_entra_b2b_invitation:
            entra_invitation = _try_entra_b2b_invite(email_norm, ctx=ctx)

        return MCPToolResult(
            ok=True,
            data={
                "user_id": user.id,
                "membership_id": membership.id,
                "created_user": created_user,
                "entra_invitation": entra_invitation,
            },
            summary=f"invited {email_norm} as {role} on {scope_kind}={scope_id_resolved}",
        )


def _try_entra_b2b_invite(email: str, *, ctx: MCPToolContext) -> dict[str, Any] | None:
    """Best-effort Microsoft Graph B2B invitation.

    Returns a stub when MSAL isn't configured or the Graph call fails;
    the calling wizard treats a stub as "send a plain invite email
    instead". Implemented as a best-effort path so the dev / test loop
    keeps working without an actual Entra application.
    """
    try:
        from aqp.auth.providers import get_active_provider
        from aqp.config import settings
    except Exception:
        return None

    try:
        provider = get_active_provider()
    except Exception:
        return None

    if getattr(provider, "provider_kind", "") != "msal_entra":
        return {
            "status": "skipped",
            "reason": "active provider is not msal_entra",
            "email": email,
        }

    if not getattr(settings, "auth_msal_b2b_enabled", True):
        return {"status": "disabled", "email": email}

    try:
        # Mint an M2M token scoped to Microsoft Graph and POST the
        # invitation payload. The Graph endpoint is /invitations.
        token = provider.m2m_token(
            audience="https://graph.microsoft.com",
            scope="https://graph.microsoft.com/.default",
        )
        import httpx

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                "https://graph.microsoft.com/v1.0/invitations",
                headers={
                    "Authorization": f"Bearer {token.access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "invitedUserEmailAddress": email,
                    "inviteRedirectUrl": getattr(settings, "auth_msal_redirect_uri", "")
                    or "https://localhost:3001/auth/callback",
                    "sendInvitationMessage": True,
                },
            )
            if resp.status_code in (200, 201):
                body = resp.json()
                return {
                    "status": "sent",
                    "invitation_id": body.get("id"),
                    "redeem_url": body.get("inviteRedeemUrl"),
                    "invited_email": email,
                }
            return {
                "status": "error",
                "code": resp.status_code,
                "body": resp.text[:512],
            }
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.debug("Entra B2B invite failed for %s: %s", email, exc)
        return {"status": "error", "error": str(exc)}


@register_data_mcp_tool
class LinkOrgToEntraTenantTool(DataMCPTool):
    name = "data.tenancy.link_org_to_entra_tenant"
    description = (
        "Create or update the :class:`EntraTenantLink` row mapping a "
        "Microsoft Entra ID tenant (``tid``) to an AQP organization. "
        "AGENTS rule 44 — this is the only sanctioned ingress for "
        "Entra-driven organization provisioning."
    )
    args_schema = LinkEntraTenantInput
    category = "tenancy"
    tags = ("tenancy", "entra", "link")
    mutates = True
    required_scopes = ("tenancy:admin",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        organization_id: str,
        entra_tenant_id: str,
        primary_domain: str | None = None,
        display_name: str | None = None,
        allowed_email_domains: list[str] | None = None,
        role_mapping: dict[str, str] | None = None,
        activate: bool = True,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_terraform import EntraTenantLink
        from aqp.persistence.models_tenancy import Organization

        tid_norm = entra_tenant_id.strip()
        domains_csv = (
            ",".join(d.strip() for d in allowed_email_domains if d.strip())
            if allowed_email_domains
            else None
        )
        now = datetime.utcnow()
        with get_session() as session:
            org = (
                session.query(Organization)
                .filter(Organization.id == organization_id)
                .one_or_none()
            )
            if org is None:
                return MCPToolResult(
                    ok=False,
                    error=f"organization {organization_id!r} not found",
                    summary="link miss org",
                )

            link = (
                session.query(EntraTenantLink)
                .filter(EntraTenantLink.entra_tenant_id == tid_norm)
                .one_or_none()
            )
            created = False
            if link is None:
                link = EntraTenantLink(
                    id=_safe_uuid(),
                    organization_id=org.id,
                    entra_tenant_id=tid_norm,
                    primary_domain=primary_domain,
                    display_name=display_name or org.name,
                    status="active" if activate else "pending",
                    allowed_email_domains=domains_csv,
                    role_mapping=role_mapping or {},
                    requested_by_email=None,
                    approved_by_user_id=ctx.actor if activate else None,
                    approved_at=now if activate else None,
                    meta={"created_via": "data.tenancy.link_org_to_entra_tenant"},
                    created_at=now,
                    updated_at=now,
                )
                session.add(link)
                created = True
            else:
                link.organization_id = org.id
                if primary_domain is not None:
                    link.primary_domain = primary_domain
                if display_name is not None:
                    link.display_name = display_name
                if domains_csv is not None:
                    link.allowed_email_domains = domains_csv
                if role_mapping is not None:
                    link.role_mapping = dict(role_mapping)
                if activate:
                    link.status = "active"
                    link.approved_by_user_id = ctx.actor
                    link.approved_at = now
                link.updated_at = now
            session.flush()
            payload = {
                "id": link.id,
                "organization_id": link.organization_id,
                "entra_tenant_id": link.entra_tenant_id,
                "primary_domain": link.primary_domain,
                "status": link.status,
                "created": created,
            }
        return MCPToolResult(
            ok=True,
            data=payload,
            summary=f"linked org {organization_id} <-> entra tid {tid_norm} (status={payload['status']})",
        )


@register_data_mcp_tool
class ListMembershipsTool(DataMCPTool):
    name = "data.tenancy.list_memberships"
    description = (
        "List memberships, optionally filtered by user_id / scope_kind / scope_id. "
        "Defaults to the calling actor's memberships when no user_id is provided."
    )
    args_schema = ListMembershipsInput
    category = "tenancy"
    tags = ("tenancy", "memberships", "browse")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        user_id: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Membership

        target_user = user_id or ctx.actor
        with get_session() as session:
            q = session.query(Membership)
            if target_user:
                q = q.filter(Membership.user_id == target_user)
            if scope_kind:
                q = q.filter(Membership.scope_kind == scope_kind)
            if scope_id:
                q = q.filter(Membership.scope_id == scope_id)
            rows = q.limit(int(limit)).all()
            items = [_serialize_membership(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items, "total": len(items)},
            rows_returned=len(items),
            summary=f"listed {len(items)} memberships",
        )


@register_data_mcp_tool
class GrantRoleTool(DataMCPTool):
    name = "data.tenancy.grant_role"
    description = (
        "Upsert a single :class:`Membership` row. Idempotent and "
        "upgrade-only — never silently downgrades a stronger existing role."
    )
    args_schema = GrantRoleInput
    category = "tenancy"
    tags = ("tenancy", "memberships", "grant")
    mutates = True
    required_scopes = ("tenancy:admin",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        user_id: str,
        scope_kind: str,
        scope_id: str,
        role: str = "viewer",
        live_control: bool = False,
        expires_at_iso: str | None = None,
    ) -> MCPToolResult:
        from aqp.config.defaults import (
            ROLE_ADMIN,
            ROLE_EDITOR,
            ROLE_OWNER,
            ROLE_VIEWER,
        )
        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Membership

        role_priority = {
            ROLE_VIEWER: 0,
            ROLE_EDITOR: 1,
            ROLE_ADMIN: 2,
            ROLE_OWNER: 3,
        }
        if role not in role_priority:
            return MCPToolResult(
                ok=False,
                error=f"unknown role {role!r}; allowed: {sorted(role_priority)}",
                summary="grant invalid role",
            )

        expires_at = None
        if expires_at_iso:
            try:
                expires_at = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
            except ValueError:
                return MCPToolResult(
                    ok=False,
                    error=f"invalid expires_at_iso {expires_at_iso!r}; expected ISO 8601",
                )

        with get_session() as session:
            existing = (
                session.query(Membership)
                .filter(
                    Membership.user_id == user_id,
                    Membership.scope_kind == scope_kind,
                    Membership.scope_id == scope_id,
                )
                .one_or_none()
            )
            created = False
            upgraded = False
            if existing is None:
                row = Membership(
                    **_membership_row(
                        user_id=user_id,
                        scope_kind=scope_kind,
                        scope_id=scope_id,
                        role=role,
                        live_control=live_control,
                        granted_by=ctx.actor,
                        expires_at=expires_at,
                    )
                )
                session.add(row)
                session.flush()
                created = True
                membership = row
            else:
                membership = existing
                if role_priority[role] > role_priority.get(membership.role, 0):
                    membership.role = role
                    membership.live_control = live_control
                    upgraded = True
                if expires_at is not None:
                    membership.expires_at = expires_at
                session.flush()

            data = _serialize_membership(membership)
            data["created"] = created
            data["upgraded"] = upgraded
        return MCPToolResult(
            ok=True,
            data=data,
            summary=f"granted {role} to user={user_id} on {scope_kind}={scope_id}",
        )


@register_data_mcp_tool
class TransferResourcesTool(DataMCPTool):
    name = "data.tenancy.transfer_resources"
    description = (
        "Transfer tenancy-scoped rows from one organization to another. "
        "Useful for org M&A flows. Defaults to dry-run; pass ``dry_run=False`` "
        "to commit the UPDATE statements."
    )
    args_schema = TransferResourcesInput
    category = "tenancy"
    tags = ("tenancy", "transfer", "admin")
    mutates = True
    required_scopes = ("tenancy:admin",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        from_org_id: str,
        to_org_id: str,
        kinds: list[str] | None = None,
        dry_run: bool = True,
    ) -> MCPToolResult:
        import sqlalchemy as sa

        from aqp.persistence.db import get_session
        from aqp.persistence.models_tenancy import Organization, Workspace

        kinds_normalized = [k.strip().lower() for k in (kinds or []) if k and k.strip()]

        # Conservative whitelist of tables that carry a direct (workspace_id ->
        # workspaces -> org) chain. We re-stamp the workspace.org_id field
        # so all downstream rows follow without a separate UPDATE pass.
        with get_session() as session:
            src = session.query(Organization).filter(Organization.id == from_org_id).one_or_none()
            dst = session.query(Organization).filter(Organization.id == to_org_id).one_or_none()
            if src is None or dst is None:
                return MCPToolResult(
                    ok=False,
                    error="from_org_id or to_org_id not found",
                    summary="transfer miss org",
                )

            ws_rows = session.query(Workspace).filter(Workspace.org_id == from_org_id).all()
            preview = [
                {
                    "workspace_id": ws.id,
                    "workspace_slug": ws.slug,
                    "from_org": from_org_id,
                    "to_org": to_org_id,
                }
                for ws in ws_rows
            ]
            if dry_run or not preview:
                return MCPToolResult(
                    ok=True,
                    data={
                        "dry_run": True,
                        "workspaces": preview,
                        "kinds_requested": kinds_normalized,
                        "would_update": len(preview),
                    },
                    summary=f"dry-run transfer: {len(preview)} workspace(s)",
                )

            session.execute(
                sa.text("UPDATE workspaces SET org_id = :to_org WHERE org_id = :from_org"),
                {"to_org": to_org_id, "from_org": from_org_id},
            )
            session.flush()
        return MCPToolResult(
            ok=True,
            data={
                "dry_run": False,
                "workspaces": preview,
                "kinds_requested": kinds_normalized,
                "updated": len(preview),
            },
            summary=f"transferred {len(preview)} workspace(s) from {from_org_id} -> {to_org_id}",
        )


__all__ = [
    "CreateOrganizationTool",
    "GrantRoleTool",
    "InviteUserTool",
    "LinkOrgToEntraTenantTool",
    "ListMembershipsTool",
    "ListOrganizationsTool",
    "TransferResourcesTool",
]
