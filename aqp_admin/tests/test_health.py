"""Smoke tests for the unauthenticated health endpoint + admin routes.

The admin app's mutating routes go through :func:`require_admin`
which validates inbound bearers against the configured IdP. For
the local-sandbox tests we disable auth via
``AQP_ADMIN_AUTH_REQUIRED=false`` so the anonymous user (with
``admin:cluster``) sails through.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _disable_auth_for_admin_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_ADMIN_AUTH_REQUIRED", "false")
    from aqp_admin.settings import reset_settings_cache

    reset_settings_cache()


@pytest.fixture()
def client(_disable_auth_for_admin_tests: None) -> TestClient:
    # Build the app AFTER the settings cache is reset so the
    # auth_required=false flag is honoured.
    from aqp_admin.main import create_app

    return TestClient(create_app())


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/admin/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


def test_accounts_organizations_returns_envelope(client: TestClient) -> None:
    """Without a monolith reachable the broker returns []; the route shape stays stable."""
    response = client.get("/admin/accounts/organizations")
    assert response.status_code == 200
    body = response.json()
    assert "organizations" in body
    assert isinstance(body["organizations"], list)


def test_services_returns_envelope(client: TestClient) -> None:
    response = client.get("/admin/services")
    assert response.status_code == 200
    body = response.json()
    assert "services" in body
    assert isinstance(body["services"], list)


def test_root_lists_endpoints(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "aqp-admin"
    assert "endpoints" in body
    assert "halt_all" in body["endpoints"]
