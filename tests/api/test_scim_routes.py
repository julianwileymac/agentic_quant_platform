"""SCIM 2.0 route contract tests."""
from __future__ import annotations

import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqp.api.routes.scim import router


def _client(monkeypatch, token: str = "secret-token") -> TestClient:
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_scim_enabled", True, raising=True)
    monkeypatch.setattr(
        settings,
        "auth_scim_bearer_token_hash",
        hashlib.sha256(token.encode("utf-8")).hexdigest(),
        raising=True,
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_scim_service_provider_config_requires_bearer(monkeypatch):
    client = _client(monkeypatch)
    res = client.get("/scim/v2/ServiceProviderConfig")
    assert res.status_code == 401


def test_scim_service_provider_config(monkeypatch):
    client = _client(monkeypatch)
    res = client.get(
        "/scim/v2/ServiceProviderConfig",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["patch"]["supported"] is True
    assert body["authenticationSchemes"][0]["type"] == "oauthbearertoken"


def test_scim_schemas_and_resource_types(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer secret-token"}
    schemas = client.get("/scim/v2/Schemas", headers=headers)
    resources = client.get("/scim/v2/ResourceTypes", headers=headers)
    assert schemas.status_code == 200
    assert resources.status_code == 200
    names = {r["name"] for r in resources.json()["Resources"]}
    assert {"User", "Group"} <= names


def test_scim_disabled_returns_404(monkeypatch):
    from aqp.config import settings

    monkeypatch.setattr(settings, "auth_scim_enabled", False, raising=True)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.get(
        "/scim/v2/ServiceProviderConfig",
        headers={"Authorization": "Bearer anything"},
    )
    assert res.status_code == 404
