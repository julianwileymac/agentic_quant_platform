from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from aqp.persistence.models_audit import (
    TenancyInvite,
    generate_invite_token,
    hash_invite_token,
)
from aqp.persistence.models_tenancy import Membership, Organization, User, Workspace


def _prepare_schema(session: OrmSession) -> None:
    from aqp.persistence import models_audit, models_tenancy  # noqa: F401
    from aqp.persistence.models import Base

    session.execute(sa.text("PRAGMA foreign_keys = ON"))
    Base.metadata.create_all(bind=session.get_bind())


def _create_org(session: OrmSession, *, slug: str, name: str) -> Organization:
    row = Organization(slug=slug, name=name)
    session.add(row)
    session.flush()
    return row


def _create_workspace(
    session: OrmSession,
    *,
    org_id: str,
    slug: str,
    name: str,
) -> Workspace:
    row = Workspace(org_id=org_id, slug=slug, name=name)
    session.add(row)
    session.flush()
    return row


def _create_user(
    session: OrmSession,
    *,
    user_id: str,
    email: str,
    display_name: str,
) -> User:
    row = User(
        id=user_id,
        email=email,
        display_name=display_name,
        auth_provider="local",
        auth_subject=f"local|{user_id}",
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


def _seed_invite(
    session: OrmSession,
    *,
    organization_id: str,
    email: str,
    status: str = "pending",
    invited_by_user_id: str | None = None,
    workspace_id: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[TenancyInvite, str]:
    raw_token, token_hash = generate_invite_token()
    row = TenancyInvite(
        organization_id=organization_id,
        workspace_id=workspace_id,
        email=email.lower(),
        role="viewer",
        invited_by_user_id=invited_by_user_id,
        token_hash=token_hash,
        token_prefix=raw_token[:8],
        status=status,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(hours=24)),
    )
    session.add(row)
    session.flush()
    return row, raw_token


def _headers(user_id: str) -> dict[str, str]:
    return {"X-AQP-User": user_id}


@pytest.fixture
def client(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import invites as invites_routes
    from aqp.config import settings

    Session = in_memory_db
    monkeypatch.setattr(settings, "auth_provider", "local", raising=False)
    monkeypatch.setattr(settings, "auth_enforce", "strict", raising=False)
    monkeypatch.setattr(settings, "auth_invite_secret", "test-invite-secret", raising=False)
    monkeypatch.setattr(settings, "auth_invite_ttl_hours", 24, raising=False)

    with Session() as session:
        _prepare_schema(session)

    @contextmanager
    def _patched_get_session():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(invites_routes, "get_session", _patched_get_session)

    app = FastAPI()
    app.include_router(invites_routes.router)
    app.include_router(invites_routes.public_router)
    return TestClient(app)


def test_create_invite_returns_raw_token_once(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-create", name="Org Create")
        workspace = _create_workspace(
            session,
            org_id=org.id,
            slug="ws-create",
            name="Workspace Create",
        )
        admin = _create_user(
            session,
            user_id="user-admin-create",
            email="admin.create@example.com",
            display_name="Admin Create",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org.id, role="admin")
        session.commit()
        org_id = org.id
        workspace_id = workspace.id
        admin_id = admin.id

    response = client.post(
        "/tenancy/invites",
        json={
            "email": "invitee@example.com",
            "organization_id": org_id,
            "workspace_id": workspace_id,
            "role": "viewer",
        },
        headers=_headers(admin_id),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["raw_token"]
    assert payload["accept_url"]

    Session = in_memory_db
    with Session() as session:
        row = session.query(TenancyInvite).filter(TenancyInvite.id == payload["id"]).one()
        assert row.token_hash == hash_invite_token(payload["raw_token"])
        assert row.token_prefix == payload["raw_token"][:8]


def test_create_invite_idempotent_for_same_pending(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-idempotent", name="Org Idempotent")
        admin = _create_user(
            session,
            user_id="user-admin-idempotent",
            email="admin.idempotent@example.com",
            display_name="Admin Idempotent",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org.id, role="admin")
        session.commit()
        org_id = org.id
        admin_id = admin.id

    payload = {
        "email": "same@example.com",
        "organization_id": org_id,
        "role": "viewer",
    }
    first = client.post("/tenancy/invites", json=payload, headers=_headers(admin_id))
    second = client.post("/tenancy/invites", json=payload, headers=_headers(admin_id))
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    first_body = first.json()
    second_body = second.json()
    assert first_body["id"] == second_body["id"]
    assert second_body["raw_token"] == ""
    assert second_body["accept_url"] == ""

    with Session() as session:
        count = (
            session.query(TenancyInvite)
            .filter(
                TenancyInvite.organization_id == org_id,
                TenancyInvite.email == "same@example.com",
                TenancyInvite.status == "pending",
            )
            .count()
        )
        assert count == 1


def test_create_invite_admin_only(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-admin-only", name="Org Admin Only")
        member = _create_user(
            session,
            user_id="user-viewer-only",
            email="viewer@example.com",
            display_name="Viewer",
        )
        _grant_org_role(session, user_id=member.id, org_id=org.id, role="viewer")
        session.commit()
        org_id = org.id
        member_id = member.id

    response = client.post(
        "/tenancy/invites",
        json={
            "email": "target@example.com",
            "organization_id": org_id,
            "role": "viewer",
        },
        headers=_headers(member_id),
    )
    assert response.status_code == 403


def test_create_invite_validates_workspace_belongs_to_org(
    client: TestClient,
    in_memory_db,
) -> None:
    Session = in_memory_db
    with Session() as session:
        org_a = _create_org(session, slug="org-a", name="Org A")
        org_b = _create_org(session, slug="org-b", name="Org B")
        workspace_b = _create_workspace(
            session,
            org_id=org_b.id,
            slug="ws-b",
            name="Workspace B",
        )
        admin = _create_user(
            session,
            user_id="user-admin-org-a",
            email="admin.a@example.com",
            display_name="Admin Org A",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org_a.id, role="admin")
        session.commit()
        org_a_id = org_a.id
        workspace_b_id = workspace_b.id
        admin_id = admin.id

    response = client.post(
        "/tenancy/invites",
        json={
            "email": "target@example.com",
            "organization_id": org_a_id,
            "workspace_id": workspace_b_id,
            "role": "viewer",
        },
        headers=_headers(admin_id),
    )
    assert response.status_code in {400, 404}


def test_list_invites_filters_by_status_and_org(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org_a = _create_org(session, slug="org-list-a", name="Org List A")
        org_b = _create_org(session, slug="org-list-b", name="Org List B")
        admin = _create_user(
            session,
            user_id="user-admin-list",
            email="admin.list@example.com",
            display_name="Admin List",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org_a.id, role="admin")

        for idx in range(3):
            _seed_invite(
                session,
                organization_id=org_a.id,
                email=f"pending-{idx}@example.com",
                status="pending",
                invited_by_user_id=admin.id,
            )
        for idx in range(2):
            _seed_invite(
                session,
                organization_id=org_a.id,
                email=f"revoked-{idx}@example.com",
                status="revoked",
                invited_by_user_id=admin.id,
            )
        _seed_invite(
            session,
            organization_id=org_b.id,
            email="pending-other-org@example.com",
            status="pending",
            invited_by_user_id=admin.id,
        )
        session.commit()
        org_a_id = org_a.id
        admin_id = admin.id

    response = client.get(
        "/tenancy/invites",
        params={"organization_id": org_a_id, "status": "pending"},
        headers=_headers(admin_id),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 3
    assert len(payload["invites"]) == 3
    assert {row["status"] for row in payload["invites"]} == {"pending"}
    assert {row["organization_id"] for row in payload["invites"]} == {org_a_id}


def test_revoke_invite_admin_only(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-revoke", name="Org Revoke")
        admin = _create_user(
            session,
            user_id="user-admin-revoke",
            email="admin.revoke@example.com",
            display_name="Admin Revoke",
        )
        viewer = _create_user(
            session,
            user_id="user-viewer-revoke",
            email="viewer.revoke@example.com",
            display_name="Viewer Revoke",
        )
        _grant_org_role(session, user_id=admin.id, org_id=org.id, role="admin")
        _grant_org_role(session, user_id=viewer.id, org_id=org.id, role="viewer")
        invite, _ = _seed_invite(
            session,
            organization_id=org.id,
            email="target.revoke@example.com",
            invited_by_user_id=admin.id,
        )
        session.commit()
        invite_id = invite.id
        viewer_id = viewer.id
        admin_id = admin.id

    denied = client.delete(f"/tenancy/invites/{invite_id}", headers=_headers(viewer_id))
    assert denied.status_code == 403

    allowed = client.delete(f"/tenancy/invites/{invite_id}", headers=_headers(admin_id))
    assert allowed.status_code == 204, allowed.text

    with Session() as session:
        row = session.query(TenancyInvite).filter(TenancyInvite.id == invite_id).one()
        assert row.status == "revoked"
        assert row.revoked_by_user_id == admin_id


def test_accept_invite_public_endpoint(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-public-accept", name="Org Public Accept")
        invite, raw_token = _seed_invite(
            session,
            organization_id=org.id,
            email="public.accept@example.com",
        )
        session.commit()
        invite_org_id = invite.organization_id

    response = client.post(f"/tenancy/invites/{raw_token}/accept")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["organization_id"] == invite_org_id
    assert payload["redirect_url"]


def test_accept_invite_404_when_unknown_token(client: TestClient) -> None:
    response = client.post(f"/tenancy/invites/{'ab' * 32}/accept")
    assert response.status_code == 404


def test_accept_invite_410_when_expired(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-expired", name="Org Expired")
        _, raw_token = _seed_invite(
            session,
            organization_id=org.id,
            email="expired@example.com",
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        session.commit()

    response = client.post(f"/tenancy/invites/{raw_token}/accept")
    assert response.status_code == 410


def test_accept_invite_410_when_already_claimed(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-claimed", name="Org Claimed")
        _, raw_token = _seed_invite(
            session,
            organization_id=org.id,
            email="claimed@example.com",
            status="claimed",
        )
        session.commit()

    response = client.post(f"/tenancy/invites/{raw_token}/accept")
    assert response.status_code == 410


def test_accept_invite_transitions_pending_to_claimed(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        org = _create_org(session, slug="org-transition", name="Org Transition")
        invite, raw_token = _seed_invite(
            session,
            organization_id=org.id,
            email="transition@example.com",
            status="pending",
        )
        session.commit()
        invite_id = invite.id

    first = client.post(f"/tenancy/invites/{raw_token}/accept")
    assert first.status_code == 200, first.text

    with Session() as session:
        row = session.query(TenancyInvite).filter(TenancyInvite.id == invite_id).one()
        assert row.status == "claimed"

    second = client.post(f"/tenancy/invites/{raw_token}/accept")
    assert second.status_code == 410

