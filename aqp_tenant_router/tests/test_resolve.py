"""Smoke tests for the resolve + ext_authz routes (Phase 3 §6.4)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from starlette.testclient import TestClient

from aqp_tenant_router.cache import CellCache, CellEntry
from aqp_tenant_router.main import _CACHE, create_app


def _stub_cache(entries: list[CellEntry]) -> CellCache:
    """Build a CellCache with the given entries pre-loaded (no HTTP refresh)."""
    cache = CellCache(control_plane_url="http://stub", refresh_interval_seconds=3600.0)
    cache._entries = {e.id: e for e in entries}  # noqa: SLF001
    cache._tenant_pinnings = {
        tenant: e.id for e in entries for tenant in e.pinned_tenants
    }
    cache._hydrated = True
    return cache


@pytest.fixture
def stub_cells():
    return [
        CellEntry(
            id="cell-shared-std-local",
            tier="shared-std",
            tenancy_strategy="shared_schema_rls",
            region="local",
            availability_zone="local-1",
            k8s_namespace="aqp",
            state="active",
            capacity_max_tenants=100,
            pinned_tenants=(),
            routes={"api": "http://localhost:8000"},
        ),
        CellEntry(
            id="cell-silo-reg-acme",
            tier="silo-reg",
            tenancy_strategy="database_per_enterprise",
            region="us-east-1",
            availability_zone="us-east-1a",
            k8s_namespace="cell-silo-reg-acme",
            state="active",
            capacity_max_tenants=1,
            pinned_tenants=("tenant_acme",),
            routes={"api": "https://acme.silo-reg.aqp.fund"},
        ),
    ]


@pytest.fixture
def client(monkeypatch, stub_cells):
    cache = _stub_cache(stub_cells)
    monkeypatch.setattr("aqp_tenant_router.main._CACHE", cache)
    # Skip the network refresh in lifespan.

    async def _no_refresh(self):  # type: ignore[no-untyped-def]
        self._hydrated = True

    monkeypatch.setattr(
        "aqp_tenant_router.cache.CellCache.start", _no_refresh
    )

    async def _no_stop(self):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr("aqp_tenant_router.cache.CellCache.stop", _no_stop)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["cells"] == 2


def test_resolve_pinned_tenant(client):
    r = client.post(
        "/resolve",
        json={"user_id": "u1", "tenant_id": "tenant_acme"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["cell_id"] == "cell-silo-reg-acme"
    assert body["tier"] == "silo-reg"
    assert body["region"] == "us-east-1"


def test_resolve_unpinned_falls_back(client):
    r = client.post("/resolve", json={"user_id": "u1"})
    assert r.status_code == 200
    body = r.json()
    assert body["cell_id"] == "cell-shared-std-local"


def test_ext_authz_anonymous_allows_with_default_cell(client):
    """No JWT in the inbound headers -> route to the default shared cell."""
    r = client.post(
        "/ext_authz/v3/check",
        json={"attributes": {"request": {"http": {"headers": {}}}}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"]["code"] == 0
    headers = body["ok_response"]["headers"]
    cell_header = next(h for h in headers if h["header"]["key"] == "x-aqp-cell")
    assert cell_header["header"]["value"] == "cell-shared-std-local"


def test_ext_authz_invalid_jwt_denied(client):
    r = client.post(
        "/ext_authz/v3/check",
        json={
            "attributes": {
                "request": {
                    "http": {
                        "headers": {"authorization": "Bearer not.a.jwt"},
                    }
                }
            }
        },
    )
    assert r.status_code == 403
    body = r.json()
    assert body["status"]["code"] == 7
