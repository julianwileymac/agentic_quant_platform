"""Smoke test for the unauthenticated health endpoint."""
from __future__ import annotations

from fastapi.testclient import TestClient

from aqp_admin.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/admin/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "version" in payload


def test_accounts_organizations_returns_empty_stub() -> None:
    response = client.get("/admin/accounts/organizations")
    assert response.status_code == 200
    assert response.json() == {"organizations": []}


def test_services_returns_empty_stub() -> None:
    response = client.get("/admin/services")
    assert response.status_code == 200
    assert response.json() == {"services": []}
