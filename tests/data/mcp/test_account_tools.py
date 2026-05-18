from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session as OrmSession

from aqp.auth import management_api as mgmt_module
from aqp.data.mcp.base import MCPPolicyError, MCPToolContext
from aqp.data.mcp.tools import account as account_tools
from aqp.persistence.models_audit import SecurityAuditEvent, TenancyInvite, generate_invite_token
from aqp.persistence.models_tenancy import Membership, Organization, User, Workspace


def _prepare_schema(session: OrmSession) -> None:
    from aqp.persistence import models_audit, models_tenancy  # noqa: F401
    from aqp.persistence.models import Base

    session.execute(sa.text("PRAGMA foreign_keys = ON"))
    Base.metadata.create_all(bind=session.get_bind())


def _create_org(session: OrmSession, *, slug: str) -> Organization:
    row = Organization(slug=slug, name=slug.replace("-", " ").title())
    session.add(row)
    session.flush()
    return row


def _create_workspace(session: OrmSession, *, org_id: str, slug: str) -> Workspace:
    row = Workspace(org_id=org_id, slug=slug, name=slug.replace("-", " ").title())
    session.add(row)
    session.flush()
    return row


def _create_user(
    session: OrmSession,
    *,
    user_id: str,
    email: str,
    auth_subject: str | None,
) -> User:
    row = User(
        id=user_id,
        email=email,
        display_name=email.split("@", 1)[0],
        auth_provider="auth0" if auth_subject and "|" in auth_subject else "local",
        auth_subject=auth_subject,
        status="active",
    )
    session.add(row)
    session.flush()
    return row


def _grant_org_role(
    session: OrmSession,
    *,
    user_id: str,
    org_id: str,
    role: str,
) -> Membership:
    row = Membership(
        user_id=user_id,
        scope_kind="org",
        scope_id=org_id,
        role=role,
        live_control=role in {"admin", "owner"},
    )
    session.add(row)
    session.flush()
    return row


def _grant_workspace_role(
    session: OrmSession,
    *,
    user_id: str,
    workspace_id: str,
    role: str = "viewer",
) -> Membership:
    row = Membership(
        user_id=user_id,
        scope_kind="workspace",
        scope_id=workspace_id,
        role=role,
        live_control=False,
    )
    session.add(row)
    session.flush()
    return row


def _seed_audit_event(
    session: OrmSession,
    *,
    user_id: str,
    event_type: str,
    created_at: datetime,
) -> SecurityAuditEvent:
    row = SecurityAuditEvent(
        user_id=user_id,
        event_type=event_type,
        event_category="account",
        severity="info",
        source="api",
        details={"event_type": event_type},
        created_at=created_at,
    )
    session.add(row)
    session.flush()
    return row


def _seed_invite(
    session: OrmSession,
    *,
    organization_id: str,
    email: str,
    invited_by_user_id: str | None = None,
    status: str = "pending",
) -> TenancyInvite:
    raw_token, token_hash = generate_invite_token()
    row = TenancyInvite(
        organization_id=organization_id,
        email=email,
        role="viewer",
        invited_by_user_id=invited_by_user_id,
        token_hash=token_hash,
        token_prefix=raw_token[:8],
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    session.add(row)
    session.flush()
    return row


def _ctx(*, actor: str, workspace_id: str) -> MCPToolContext:
    return MCPToolContext(
        actor=actor,
        actor_kind="user",
        workspace_id=workspace_id,
        granted_scopes=("data:read",),
    )


@pytest.fixture
def session_factory(in_memory_db, monkeypatch: pytest.MonkeyPatch):
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_invite_secret", "test-invite-secret", raising=False)
    Session = in_memory_db
    with Session() as session:
        _prepare_schema(session)
    return Session


@pytest.fixture
def management_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock(spec=mgmt_module.Auth0ManagementClient)
    monkeypatch.setattr(account_tools, "get_management_client", lambda: client)
    return client


def test_whoami_tool_returns_actor_profile(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-whoami")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-whoami")
        user = _create_user(
            session,
            user_id="user-whoami",
            email="whoami@example.com",
            auth_subject="local-user-whoami",
        )
        _grant_workspace_role(session, user_id=user.id, workspace_id=workspace.id)
        session.commit()
        user_id = user.id
        workspace_id = workspace.id

    result = account_tools.AccountWhoAmITool().run(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    assert result.data["email"] == "whoami@example.com"


def test_list_sessions_returns_empty_with_warning_when_no_auth0_subject(
    session_factory: Any,
) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-no-auth0")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-no-auth0")
        user = _create_user(
            session,
            user_id="user-no-auth0",
            email="noauth0@example.com",
            auth_subject="local-user-no-auth0",
        )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id

    result = account_tools.AccountListSessionsTool().invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    assert result.data == []
    assert result.warnings


def test_list_sessions_returns_dataclass_payload_when_auth0(
    session_factory: Any,
    management_client: MagicMock,
) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-auth0-sessions")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-auth0-sessions")
        user = _create_user(
            session,
            user_id="user-auth0-sessions",
            email="auth0.sessions@example.com",
            auth_subject="auth0|user-auth0-sessions",
        )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id
        auth_subject = user.auth_subject or ""

    management_client.list_user_sessions.return_value = [
        mgmt_module.Auth0Session(
            id="sess-1",
            user_id=auth_subject,
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T01:00:00Z",
            last_activity="2026-01-01T01:30:00Z",
            ip="127.0.0.1",
            user_agent="pytest-agent",
            device="desktop",
            location="US",
        ),
        mgmt_module.Auth0Session(
            id="sess-2",
            user_id=auth_subject,
            created_at="2026-01-02T00:00:00Z",
            updated_at="2026-01-02T01:00:00Z",
            last_activity="2026-01-02T01:30:00Z",
            ip="127.0.0.2",
            user_agent="pytest-agent-2",
            device="laptop",
            location="US",
        ),
    ]

    result = account_tools.AccountListSessionsTool().invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    assert len(result.data) == 2
    assert result.data[0]["id"] == "sess-1"
    assert result.data[1]["id"] == "sess-2"


def test_list_sessions_swallows_management_error_into_warning(
    session_factory: Any,
    management_client: MagicMock,
) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-auth0-error")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-auth0-error")
        user = _create_user(
            session,
            user_id="user-auth0-error",
            email="auth0.error@example.com",
            auth_subject="auth0|user-auth0-error",
        )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id

    management_client.list_user_sessions.side_effect = mgmt_module.Auth0ManagementError("boom")
    result = account_tools.AccountListSessionsTool().invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    assert result.data == []
    assert result.warnings


def test_list_factors_same_pattern(
    session_factory: Any,
    management_client: MagicMock,
) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-auth0-factors")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-auth0-factors")
        user = _create_user(
            session,
            user_id="user-auth0-factors",
            email="auth0.factors@example.com",
            auth_subject="auth0|user-auth0-factors",
        )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id

    management_client.list_authentication_methods.return_value = [
        mgmt_module.Auth0Factor(
            id="factor-1",
            type="totp",
            name="Authenticator",
            enrolled_at="2026-01-01T00:00:00Z",
            confirmed=True,
            phone_number=None,
        )
    ]
    result = account_tools.AccountListFactorsTool().invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    assert len(result.data) == 1
    assert result.data[0]["id"] == "factor-1"


def test_list_audit_events_returns_user_scoped_rows(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-audit-scope")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-audit-scope")
        user_a = _create_user(
            session,
            user_id="user-audit-a",
            email="audit.a@example.com",
            auth_subject="local-audit-a",
        )
        user_b = _create_user(
            session,
            user_id="user-audit-b",
            email="audit.b@example.com",
            auth_subject="local-audit-b",
        )
        _seed_audit_event(
            session,
            user_id=user_a.id,
            event_type="audit-a-1",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        _seed_audit_event(
            session,
            user_id=user_a.id,
            event_type="audit-a-2",
            created_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        _seed_audit_event(
            session,
            user_id=user_b.id,
            event_type="audit-b-1",
            created_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        session.commit()
        user_a_id = user_a.id
        workspace_id = workspace.id

    result = account_tools.AccountListAuditEventsTool().invoke(
        ctx=_ctx(actor=user_a_id, workspace_id=workspace_id),
    )
    assert result.ok is True
    event_types = {row["event_type"] for row in result.data}
    assert "audit-a-1" in event_types
    assert "audit-a-2" in event_types
    assert "audit-b-1" not in event_types


def test_list_audit_events_paginated(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-audit-pages")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-audit-pages")
        user = _create_user(
            session,
            user_id="user-audit-pages",
            email="audit.pages@example.com",
            auth_subject="local-audit-pages",
        )
        base = datetime(2026, 2, 1, tzinfo=UTC)
        for idx in range(25):
            _seed_audit_event(
                session,
                user_id=user.id,
                event_type=f"audit-{idx:02d}",
                created_at=base + timedelta(minutes=idx),
            )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id

    tool = account_tools.AccountListAuditEventsTool()
    page0 = tool.invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
        per_page=10,
        page=0,
    )
    page1 = tool.invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
        per_page=10,
        page=1,
    )
    page2 = tool.invoke(
        ctx=_ctx(actor=user_id, workspace_id=workspace_id),
        per_page=10,
        page=2,
    )

    assert page0.ok is True
    assert page1.ok is True
    assert page2.ok is True
    assert len(page0.data) == 10
    assert len(page1.data) == 10
    assert len(page2.data) == 5


def test_list_invites_admin_required(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-invites-policy")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-invites-policy")
        user = _create_user(
            session,
            user_id="user-invites-viewer",
            email="invites.viewer@example.com",
            auth_subject="local-invites-viewer",
        )
        _grant_org_role(session, user_id=user.id, org_id=org.id, role="viewer")
        _seed_invite(
            session,
            organization_id=org.id,
            email="invite.target@example.com",
            invited_by_user_id=user.id,
        )
        session.commit()
        user_id = user.id
        workspace_id = workspace.id
        org_id = org.id

    with pytest.raises(MCPPolicyError):
        account_tools.AccountListInvitesTool().run(
            ctx=_ctx(actor=user_id, workspace_id=workspace_id),
            organization_id=org_id,
        )


def test_list_invites_filters_by_status(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-invites-filter")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-invites-filter")
        admin = _create_user(
            session,
            user_id="user-invites-admin",
            email="invites.admin@example.com",
            auth_subject="local-invites-admin",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org.id, role="admin")
        _seed_invite(
            session,
            organization_id=org.id,
            email="pending-1@example.com",
            invited_by_user_id=admin.id,
            status="pending",
        )
        _seed_invite(
            session,
            organization_id=org.id,
            email="pending-2@example.com",
            invited_by_user_id=admin.id,
            status="pending",
        )
        _seed_invite(
            session,
            organization_id=org.id,
            email="revoked-1@example.com",
            invited_by_user_id=admin.id,
            status="revoked",
        )
        session.commit()
        admin_id = admin.id
        workspace_id = workspace.id
        org_id = org.id

    result = account_tools.AccountListInvitesTool().invoke(
        ctx=_ctx(actor=admin_id, workspace_id=workspace_id),
        organization_id=org_id,
        status="pending",
    )
    assert result.ok is True
    assert len(result.data) == 2
    assert {row["status"] for row in result.data} == {"pending"}


def test_list_invites_does_not_leak_token_hash(session_factory: Any) -> None:
    Session = session_factory
    with Session() as session:
        org = _create_org(session, slug="org-invites-redact")
        workspace = _create_workspace(session, org_id=org.id, slug="ws-invites-redact")
        admin = _create_user(
            session,
            user_id="user-invites-redact",
            email="invites.redact@example.com",
            auth_subject="local-invites-redact",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org.id, role="admin")
        _seed_invite(
            session,
            organization_id=org.id,
            email="redact-1@example.com",
            invited_by_user_id=admin.id,
        )
        session.commit()
        admin_id = admin.id
        workspace_id = workspace.id
        org_id = org.id

    result = account_tools.AccountListInvitesTool().invoke(
        ctx=_ctx(actor=admin_id, workspace_id=workspace_id),
        organization_id=org_id,
    )
    assert result.ok is True
    assert result.data
    for row in result.data:
        assert "token_prefix" in row
        assert "token_hash" not in row

