"""Smoke tests for :mod:`aqp.auth.management_api`."""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from aqp.auth.management_api import (
    Auth0ManagementClient,
    Auth0ManagementError,
    reset_management_client,
)


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    reset_management_client()
    yield
    reset_management_client()


@pytest.fixture
def _auth0_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from aqp.config import settings as _settings

    monkeypatch.setattr(
        _settings, "auth0_mgmt_api_audience", "https://tenant.auth0.com/api/v2/", raising=False
    )
    monkeypatch.setattr(_settings, "auth0_mgmt_api_client_id", "mgmt-client-id", raising=False)
    monkeypatch.setattr(
        _settings, "auth0_mgmt_api_client_secret", "mgmt-client-secret", raising=False
    )


def _mock_token(router: respx.MockRouter) -> respx.Route:
    return router.post("https://tenant.auth0.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "mgmt-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read:users",
            },
        )
    )


def test_token_cache_reuses_m2m_token(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        token_route = _mock_token(mock)
        user_route = mock.get("https://tenant.auth0.com/api/v2/users/auth0%7Cabc").mock(
            return_value=httpx.Response(200, json={"user_id": "auth0|abc"})
        )

        client.get_user("auth0|abc")
        client.get_user("auth0|abc")

    assert token_route.call_count == 1
    assert user_route.call_count == 2


def test_429_retries_then_maps_to_rate_limit_error(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        connections_route = mock.get("https://tenant.auth0.com/api/v2/connections").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(429, headers={"Retry-After": "0"}),
            ]
        )
        with pytest.raises(Auth0ManagementError, match="rate limit exceeded after retries"):
            client.list_connections()
    assert connections_route.call_count == 4


def test_maps_401_to_invalid_credentials(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        mock.get("https://tenant.auth0.com/api/v2/users/auth0%7Cblocked").mock(
            return_value=httpx.Response(401, json={"message": "bad credentials"})
        )
        with pytest.raises(Auth0ManagementError, match="invalid credentials"):
            client.get_user("auth0|blocked")


def test_maps_404_to_not_found_user_id(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        mock.get("https://tenant.auth0.com/api/v2/users/auth0%7Cmissing").mock(
            return_value=httpx.Response(404, json={"message": "missing"})
        )
        with pytest.raises(Auth0ManagementError, match=r"not found: auth0\|missing"):
            client.get_user("auth0|missing")


def test_list_user_sessions_returns_dataclasses(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        mock.get("https://tenant.auth0.com/api/v2/users/auth0%7Cabc/sessions").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "id": "sess_1",
                        "user_id": "auth0|abc",
                        "created_at": "2026-05-01T01:02:03Z",
                        "updated_at": "2026-05-01T02:02:03Z",
                        "last_activity": "2026-05-01T03:02:03Z",
                        "ip": "127.0.0.1",
                        "user_agent": "Mozilla/5.0",
                        "device": "Chrome on macOS",
                        "location": "Austin, US",
                    }
                ],
            )
        )
        sessions = client.list_user_sessions("auth0|abc")

    assert len(sessions) == 1
    assert sessions[0].id == "sess_1"
    assert sessions[0].location == "Austin, US"
    assert sessions[0].device == "Chrome on macOS"


def test_create_mfa_enrollment_ticket_happy_path(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    captured_body: dict[str, object] = {}

    def _ticket_handler(request: httpx.Request) -> httpx.Response:
        captured_body.update(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "ticket_id": "ticket_1",
                "ticket_url": "https://tenant.auth0.com/continue?ticket=ticket_1",
                "qr_code_url": "otpauth://totp/AQP:user",
                "secret": "ABCD1234",
                "recovery_codes": ["r1", "r2"],
                "expires_at": "2026-06-01T00:00:00Z",
            },
        )

    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        mock.post("https://tenant.auth0.com/api/v2/guardian/enrollments/ticket").mock(
            side_effect=_ticket_handler
        )
        ticket = client.create_mfa_enrollment_ticket(
            "auth0|abc",
            "totp",
            return_url="https://app.example.com/settings/security",
        )

    assert captured_body == {
        "user_id": "auth0|abc",
        "send_mail": False,
        "factor": "totp",
        "return_url": "https://app.example.com/settings/security",
    }
    assert ticket.ticket_id == "ticket_1"
    assert ticket.qr_code_url == "otpauth://totp/AQP:user"
    assert ticket.recovery_codes == ["r1", "r2"]


def test_create_mfa_enrollment_ticket_maps_scope_error(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        _mock_token(mock)
        mock.post("https://tenant.auth0.com/api/v2/guardian/enrollments/ticket").mock(
            return_value=httpx.Response(
                403,
                json={"message": "insufficient_scope"},
                headers={"www-authenticate": 'Bearer scope="create:guardian_enrollments"'},
            )
        )
        with pytest.raises(
            Auth0ManagementError,
            match=r"scope create:guardian_enrollments required:",
        ):
            client.create_mfa_enrollment_ticket("auth0|abc", "totp")


def test_all_methods_hit_expected_auth0_paths(_auth0_settings: None) -> None:
    client = Auth0ManagementClient()
    captured: dict[str, httpx.Request] = {}
    user_id = "auth0|primary"
    user_id_encoded = "auth0%7Cprimary"
    secondary_user_id = "google-oauth2|secondary"
    secondary_user_id_encoded = "google-oauth2%7Csecondary"

    def capture(name: str, payload: dict[str, object] | list[object] | None = None):
        def _handler(request: httpx.Request) -> httpx.Response:
            captured[name] = request
            if payload is None:
                return httpx.Response(204)
            return httpx.Response(200, json=payload)

        return _handler

    with respx.mock(using="httpcore", assert_all_called=False) as mock:
        token_route = _mock_token(mock)
        get_user_route = mock.get(f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}").mock(
            side_effect=capture("get_user", {"user_id": user_id})
        )
        update_user_route = mock.patch(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}"
        ).mock(side_effect=capture("update_user", {"user_id": user_id, "name": "new"}))
        delete_user_route = mock.delete(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}"
        ).mock(side_effect=capture("delete_user"))
        sessions_route = mock.get(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/sessions"
        ).mock(
            side_effect=[
                httpx.Response(200, json=[]),
                httpx.Response(200, json=[]),
            ]
        )
        revoke_session_route = mock.delete("https://tenant.auth0.com/api/v2/sessions/sess_1").mock(
            side_effect=capture("revoke_session")
        )
        revoke_all_route = mock.delete(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/sessions"
        ).mock(side_effect=capture("revoke_all"))
        list_methods_route = mock.get(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/authentication-methods"
        ).mock(side_effect=capture("list_methods", []))
        delete_method_route = mock.delete(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/authentication-methods/method_1"
        ).mock(side_effect=capture("delete_method"))
        mfa_route = mock.post("https://tenant.auth0.com/api/v2/guardian/enrollments/ticket").mock(
            side_effect=capture(
                "mfa_ticket",
                {
                    "ticket_id": "ticket_1",
                    "ticket_url": "https://tenant.auth0.com/continue?ticket=ticket_1",
                    "recovery_codes": [],
                    "expires_at": "2026-06-01T00:00:00Z",
                },
            )
        )
        password_route = mock.post(
            "https://tenant.auth0.com/api/v2/tickets/password-change"
        ).mock(
            side_effect=capture(
                "password_ticket",
                {"ticket": "https://tenant.auth0.com/ticket", "expires_at": "2026-06-01T00:00:00Z"},
            )
        )
        link_route = mock.post(
            f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/identities"
        ).mock(side_effect=capture("link_account", []))
        unlink_route = mock.delete(
            "https://tenant.auth0.com/api/v2/users/"
            f"{user_id_encoded}/identities/google-oauth2/{secondary_user_id_encoded}"
        ).mock(side_effect=capture("unlink_account", []))
        logs_route = mock.get(f"https://tenant.auth0.com/api/v2/users/{user_id_encoded}/logs").mock(
            side_effect=capture("list_logs", [])
        )
        connections_route = mock.get("https://tenant.auth0.com/api/v2/connections").mock(
            side_effect=capture("list_connections", [])
        )

        client.get_user(user_id)
        client.update_user(user_id, {"name": "new"})
        client.delete_user(user_id)
        client.list_user_sessions(user_id)
        client.revoke_session("sess_1")
        assert client.revoke_all_sessions_for_user(user_id) == 0
        client.list_authentication_methods(user_id)
        client.delete_authentication_method(user_id, "method_1")
        client.create_mfa_enrollment_ticket(user_id, "totp")
        client.create_password_change_ticket(
            user_id, return_url="https://app.example.com/settings/security"
        )
        client.link_account(user_id, secondary_jwt="jwt.secondary.token")
        client.unlink_account(
            user_id,
            provider="google-oauth2",
            secondary_user_id=secondary_user_id,
        )
        client.list_user_logs(user_id, per_page=25, page=2)
        client.list_connections(strategy="auth0")

    assert token_route.call_count == 1
    assert get_user_route.called
    assert update_user_route.called
    assert delete_user_route.called
    assert sessions_route.call_count == 2
    assert revoke_session_route.called
    assert revoke_all_route.called
    assert list_methods_route.called
    assert delete_method_route.called
    assert mfa_route.called
    assert password_route.called
    assert link_route.called
    assert unlink_route.called
    assert logs_route.called
    assert connections_route.called

    update_body = json.loads(captured["update_user"].content.decode("utf-8"))
    assert update_body == {"name": "new"}
    password_body = json.loads(captured["password_ticket"].content.decode("utf-8"))
    assert password_body["result_url"] == "https://app.example.com/settings/security"
    link_body = json.loads(captured["link_account"].content.decode("utf-8"))
    assert link_body == {"link_with": "jwt.secondary.token"}
    assert captured["list_logs"].url.params["per_page"] == "25"
    assert captured["list_logs"].url.params["page"] == "2"
    assert captured["list_connections"].url.params["strategy"] == "auth0"
