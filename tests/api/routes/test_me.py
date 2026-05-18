from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as OrmSession

from aqp.auth import management_api as mgmt_module
from aqp.config.defaults import DEFAULT_USER_EMAIL, DEFAULT_USER_ID
from aqp.persistence.models_audit import SecurityAuditEvent
from aqp.persistence.models_tenancy import User


def _prepare_schema(session: OrmSession) -> None:
    from aqp.persistence import models_audit, models_tenancy  # noqa: F401
    from aqp.persistence.models import Base

    session.execute(sa.text("PRAGMA foreign_keys = ON"))
    Base.metadata.create_all(bind=session.get_bind())


def _create_user(
    session: OrmSession,
    *,
    user_id: str,
    email: str,
    display_name: str,
    auth_subject: str | None,
) -> User:
    row = User(
        id=user_id,
        email=email,
        display_name=display_name,
        auth_subject=auth_subject,
        auth_provider="auth0" if auth_subject and "|" in auth_subject else "local",
        status="active",
    )
    session.add(row)
    session.flush()
    return row


def _user_headers(user_id: str) -> dict[str, str]:
    return {"X-AQP-User": user_id}


@pytest.fixture
def client(in_memory_db, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from aqp.api.routes import me as me_routes
    from aqp.config import settings

    Session = in_memory_db
    monkeypatch.setattr(settings, "auth_provider", "local", raising=False)
    monkeypatch.setattr(settings, "auth_enforce", "strict", raising=False)

    with Session() as session:
        _prepare_schema(session)

    app = FastAPI()
    app.include_router(me_routes.router)
    return TestClient(app)


@pytest.fixture
def management_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = MagicMock(spec=mgmt_module.Auth0ManagementClient)
    monkeypatch.setattr(mgmt_module, "get_management_client", lambda: client)
    return client


@pytest.fixture
def auth0_user(in_memory_db) -> dict[str, str]:
    Session = in_memory_db
    payload = {
        "id": "user-auth0-1",
        "email": "auth0.user@example.com",
        "display_name": "Auth0 User",
        "subject": "auth0|user-auth0-1",
    }
    with Session() as session:
        _create_user(
            session,
            user_id=payload["id"],
            email=payload["email"],
            display_name=payload["display_name"],
            auth_subject=payload["subject"],
        )
        session.commit()
    return payload


def test_get_me_returns_local_profile_when_not_on_auth0(client: TestClient) -> None:
    response = client.get("/me")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["auth0_user_id"] is None
    assert payload["mfa_enabled"] is False
    assert payload["factor_count"] == 0
    assert payload["session_count"] == 0


def test_get_me_enriches_when_auth0_subject(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.get_user.return_value = {
        "email_verified": True,
        "identities": [
            {
                "provider": "auth0",
                "connection": "Username-Password-Authentication",
                "user_id": "primary-user",
                "profileData": {"email": auth0_user["email"]},
            }
        ],
    }
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
    management_client.list_user_sessions.return_value = [
        mgmt_module.Auth0Session(
            id="session-1",
            user_id=auth0_user["subject"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            last_activity="2026-01-01T01:00:00Z",
            ip="127.0.0.1",
            user_agent="pytest-agent",
            device="desktop",
            location="US",
        ),
        mgmt_module.Auth0Session(
            id="session-2",
            user_id=auth0_user["subject"],
            created_at="2026-01-02T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            last_activity="2026-01-02T01:00:00Z",
            ip="127.0.0.2",
            user_agent="pytest-agent-2",
            device="laptop",
            location="US",
        ),
    ]

    response = client.get("/me", headers=_user_headers(auth0_user["id"]))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["auth0_user_id"] == auth0_user["subject"]
    assert payload["mfa_enabled"] is True
    assert payload["factor_count"] == 1
    assert payload["session_count"] == 2
    assert payload["email_verified"] is True


def test_patch_me_updates_local_and_auth0(
    client: TestClient,
    in_memory_db,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.get_user.return_value = {"identities": []}
    management_client.list_authentication_methods.return_value = []
    management_client.list_user_sessions.return_value = []
    management_client.update_user.return_value = {}

    response = client.patch(
        "/me",
        json={
            "display_name": "Renamed User",
            "avatar_url": "https://cdn.example/avatar.png",
        },
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 200, response.text
    management_client.update_user.assert_called_once_with(
        auth0_user["subject"],
        {"name": "Renamed User"},
    )

    Session = in_memory_db
    with Session() as session:
        row = session.query(User).filter(User.id == auth0_user["id"]).one()
        assert row.display_name == "Renamed User"
        assert row.avatar_url == "https://cdn.example/avatar.png"


def test_change_password_returns_ticket_url(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.create_password_change_ticket.return_value = (
        mgmt_module.Auth0PasswordTicket(
            ticket="https://auth.example.com/ticket/change-password",
            expires_at="2026-01-01T12:00:00Z",
        )
    )

    response = client.post(
        "/me/change-password",
        json={"return_url": "https://app.example.com/account"},
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ticket_url"] == "https://auth.example.com/ticket/change-password"
    assert payload["expires_at"] == "2026-01-01T12:00:00Z"


def test_list_mfa_factors_proxies_management_api(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.list_authentication_methods.return_value = [
        mgmt_module.Auth0Factor(
            id="factor-1",
            type="totp",
            name="Authenticator",
            enrolled_at="2026-01-01T00:00:00Z",
            confirmed=True,
            phone_number=None,
        ),
        mgmt_module.Auth0Factor(
            id="factor-2",
            type="sms",
            name="Phone",
            enrolled_at="2026-01-02T00:00:00Z",
            confirmed=True,
            phone_number="***1234",
        ),
    ]

    response = client.get("/me/mfa/factors", headers=_user_headers(auth0_user["id"]))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["id"] == "factor-1"
    assert payload[1]["type"] == "sms"


def test_post_mfa_enroll_returns_enrollment_payload(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.create_mfa_enrollment_ticket.return_value = (
        mgmt_module.Auth0MfaEnrollmentTicket(
            ticket_id="enroll-1",
            ticket_url="https://auth.example.com/guardian/enroll-1",
            qr_code_url="otpauth://totp/AQP?secret=ABC123",
            secret="ABC123",
            recovery_codes=["code-1", "code-2"],
            expires_at="2026-01-01T12:00:00Z",
        )
    )

    response = client.post(
        "/me/mfa/enroll",
        json={"factor": "totp", "return_url": "https://app.example.com/account/security"},
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["qr_code_url"] == "otpauth://totp/AQP?secret=ABC123"
    assert payload["secret"] == "ABC123"
    assert payload["recovery_codes"] == ["code-1", "code-2"]


def test_delete_mfa_factor_returns_204(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    response = client.delete(
        "/me/mfa/factors/factor-1",
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 204, response.text
    management_client.delete_authentication_method.assert_called_once_with(
        auth0_user["subject"],
        "factor-1",
    )


def test_list_sessions_returns_dataclass_payload(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.list_user_sessions.return_value = [
        mgmt_module.Auth0Session(
            id="session-1",
            user_id=auth0_user["subject"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            last_activity="2026-01-01T00:30:00Z",
            ip="127.0.0.1",
            user_agent="pytest-agent",
            device="desktop",
            location="US",
        ),
        mgmt_module.Auth0Session(
            id="session-2",
            user_id=auth0_user["subject"],
            created_at="2026-01-02T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            last_activity="2026-01-02T00:30:00Z",
            ip="127.0.0.2",
            user_agent="pytest-agent-2",
            device="laptop",
            location="US",
        ),
    ]

    response = client.get("/me/sessions", headers=_user_headers(auth0_user["id"]))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["id"] == "session-1"
    assert payload[1]["id"] == "session-2"


def test_delete_session_404_when_not_owned(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.list_user_sessions.return_value = [
        mgmt_module.Auth0Session(
            id="session-1",
            user_id=auth0_user["subject"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            last_activity=None,
            ip=None,
            user_agent=None,
            device=None,
            location=None,
        )
    ]

    response = client.delete(
        "/me/sessions/session-not-owned",
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 404
    management_client.revoke_session.assert_not_called()


def test_delete_session_revokes_when_owned(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.list_user_sessions.return_value = [
        mgmt_module.Auth0Session(
            id="session-1",
            user_id=auth0_user["subject"],
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            last_activity=None,
            ip=None,
            user_agent=None,
            device=None,
            location=None,
        ),
        mgmt_module.Auth0Session(
            id="session-2",
            user_id=auth0_user["subject"],
            created_at="2026-01-02T00:00:00Z",
            updated_at="2026-01-02T00:00:00Z",
            last_activity=None,
            ip=None,
            user_agent=None,
            device=None,
            location=None,
        ),
    ]

    response = client.delete(
        "/me/sessions/session-2",
        headers=_user_headers(auth0_user["id"]),
    )
    assert response.status_code == 204, response.text
    management_client.revoke_session.assert_called_once_with("session-2")


def test_delete_all_sessions_returns_count(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.revoke_all_sessions_for_user.return_value = 3

    response = client.delete("/me/sessions", headers=_user_headers(auth0_user["id"]))
    assert response.status_code == 200, response.text
    assert response.json() == {"revoked": 3}


def test_list_connected_accounts_projects_identities(
    client: TestClient,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.get_user.return_value = {
        "identities": [
            {
                "provider": "auth0",
                "connection": "Username-Password-Authentication",
                "user_id": "primary-user",
                "isSocial": False,
                "profileData": {"email": auth0_user["email"]},
            },
            {
                "provider": "google-oauth2",
                "connection": "google-oauth2",
                "user_id": "google-user",
                "isSocial": True,
                "profileData": {"email": auth0_user["email"]},
            },
        ]
    }

    response = client.get("/me/connected-accounts", headers=_user_headers(auth0_user["id"]))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["provider"] == "auth0"
    assert payload[0]["is_primary"] is True
    assert payload[1]["provider"] == "google-oauth2"
    assert payload[1]["is_primary"] is False


def test_audit_returns_paginated_local_events(client: TestClient, in_memory_db) -> None:
    Session = in_memory_db
    with Session() as session:
        _create_user(
            session,
            user_id=DEFAULT_USER_ID,
            email=DEFAULT_USER_EMAIL,
            display_name="Local User",
            auth_subject="local",
        )
        _create_user(
            session,
            user_id="other-user",
            email="other@example.com",
            display_name="Other User",
            auth_subject="local-other",
        )
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for idx in range(5):
            session.add(
                SecurityAuditEvent(
                    user_id=DEFAULT_USER_ID,
                    event_type=f"event-{idx}",
                    event_category="account",
                    severity="info",
                    source="api",
                    details={"idx": idx},
                    created_at=base + timedelta(minutes=idx),
                )
            )
        session.add(
            SecurityAuditEvent(
                user_id="other-user",
                event_type="other-event",
                event_category="account",
                severity="info",
                source="api",
                details={},
                created_at=base + timedelta(minutes=10),
            )
        )
        session.commit()

    response = client.get("/me/audit", params={"per_page": 2, "page": 1})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 5
    assert payload["page"] == 1
    assert payload["per_page"] == 2
    assert [event["event_type"] for event in payload["events"]] == ["event-2", "event-1"]


def test_delete_me_requires_confirm_header(
    client: TestClient,
    in_memory_db,
    auth0_user: dict[str, str],
    management_client: MagicMock,
) -> None:
    management_client.revoke_all_sessions_for_user.return_value = 2

    headers = _user_headers(auth0_user["id"])
    missing_confirm = client.delete("/me", headers=headers)
    assert missing_confirm.status_code == 400

    wrong_confirm = client.delete(
        "/me",
        headers={**headers, "X-AQP-Confirm-Email": "wrong@example.com"},
    )
    assert wrong_confirm.status_code == 400

    correct_confirm = client.delete(
        "/me",
        headers={**headers, "X-AQP-Confirm-Email": auth0_user["email"]},
    )
    assert correct_confirm.status_code == 200, correct_confirm.text
    assert correct_confirm.json() == {"status": "deleted"}

    management_client.revoke_all_sessions_for_user.assert_called_once_with(auth0_user["subject"])
    management_client.delete_user.assert_called_once_with(auth0_user["subject"])

    Session = in_memory_db
    with Session() as session:
        row = session.query(User).filter(User.id == auth0_user["id"]).one()
        assert row.status == "deleted"
        assert row.auth_subject is None
        assert row.email.startswith(f"deleted-{auth0_user['id']}@")

