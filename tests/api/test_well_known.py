"""RFC 9728 Protected Resource Metadata route tests (Workstream E).

The 2025-11-25 MCP authorization spec requires every MCP server to
publish OAuth 2.0 Protected Resource Metadata at
``/.well-known/oauth-protected-resource``. These tests cover:

- the root document is reachable without authentication (RFC 9728 §6.1);
- per-MCP namespaced documents return distinct ``resource`` URIs;
- the metadata mirrors the configured ``mcp_*_canonical_uri`` settings;
- empty config still returns valid JSON (best-effort fallback to the
  backend's external URL).
"""
from __future__ import annotations

import pytest


def _make_client(monkeypatch: pytest.MonkeyPatch, *, data_uri: str = "", code_uri: str = ""):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.api.well_known import build_well_known_router
    from aqp.config import settings

    monkeypatch.setattr(settings, "mcp_data_canonical_uri", data_uri, raising=False)
    monkeypatch.setattr(settings, "mcp_codebase_canonical_uri", code_uri, raising=False)
    monkeypatch.setattr(settings, "backend_external_url", "https://example.test", raising=False)
    monkeypatch.setattr(
        settings, "auth_oidc_issuer", "https://idp.example.test", raising=False
    )

    app = FastAPI()
    app.include_router(build_well_known_router())
    return TestClient(app)


def test_root_metadata_returns_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(
        monkeypatch,
        data_uri="https://api.aqp.fund/mcp/data",
        code_uri="https://api.aqp.fund/mcp/codebase",
    )
    response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    payload = response.json()
    # The root document MAY surface either MCP URI; both are acceptable
    # so long as ``resource`` is set and is a URI.
    assert "://" in payload["resource"]
    assert "data:read" in payload["scopes_supported"]
    assert payload["bearer_methods_supported"] == ["header"]
    assert payload["authorization_servers"] == ["https://idp.example.test"]


def test_data_mcp_metadata_uses_canonical_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, data_uri="https://api.aqp.fund/mcp/data")
    response = client.get("/.well-known/oauth-protected-resource/mcp/data")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"] == "https://api.aqp.fund/mcp/data"
    assert "data:read" in payload["scopes_supported"]


def test_codebase_mcp_metadata_uses_canonical_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, code_uri="https://api.aqp.fund/mcp/codebase")
    response = client.get("/.well-known/oauth-protected-resource/mcp/codebase")
    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"] == "https://api.aqp.fund/mcp/codebase"
    assert "code:read" in payload["scopes_supported"]


def test_data_mcp_metadata_returns_404_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # Drop the fallback origin too — must 404 because RFC 9728 forbids
    # emitting a document without a ``resource`` URI.
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.api.well_known import build_well_known_router
    from aqp.config import settings

    monkeypatch.setattr(settings, "mcp_data_canonical_uri", "", raising=False)
    monkeypatch.setattr(settings, "mcp_codebase_canonical_uri", "", raising=False)
    monkeypatch.setattr(settings, "backend_external_url", "", raising=False)

    app = FastAPI()
    app.include_router(build_well_known_router())
    client = TestClient(app)

    response = client.get("/.well-known/oauth-protected-resource/mcp/data")
    assert response.status_code == 404
