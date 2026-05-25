"""Settings router tests (framework config + cloud onboarding)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aqp_admin.integrations.broker import AdminBrokerError


@pytest.fixture(autouse=True)
def _disable_auth_for_admin_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_ADMIN_AUTH_REQUIRED", "false")
    from aqp_admin.settings import reset_settings_cache

    reset_settings_cache()


@pytest.fixture()
def client(_disable_auth_for_admin_tests: None) -> TestClient:
    from aqp_admin.main import create_app

    return TestClient(create_app())


@dataclass
class _StubControlPlane:
    should_fail_patch: bool = False
    patch_calls: list[dict[str, Any]] = field(default_factory=list)

    async def get_config(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {"service_id": service_id, "namespace": namespace, "values": {"AQP_ADMIN_API_URL": "http://localhost:8900"}},
        }

    async def patch_config(
        self,
        service_id: str,
        body: dict[str, Any],
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        self.patch_calls.append({"service_id": service_id, "namespace": namespace, "body": body})
        if self.should_fail_patch:
            raise AdminBrokerError(
                "control plane unavailable",
                code="upstream_unreachable",
                status_code=503,
            )
        return {"status": "ok", "data": {"service_id": service_id, "updated": list((body.get("values") or {}).keys())}}

    async def telemetry_snapshot(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": "ok",
            "data": {
                "provider": "kubernetes",
                "status": "healthy",
                "available": True,
                "metadata": {"cluster": "dev"},
            },
        }


@dataclass
class _StubMonolith:
    create_calls: list[dict[str, Any]] = field(default_factory=list)

    async def list_terraform_providers(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {
            "items": [
                {"kind": "aws", "slug": "aws-prod", "name": "AWS prod"},
                {"kind": "azure", "slug": "azure-prod", "name": "Azure prod"},
            ]
        }

    async def create_terraform_provider(
        self,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        self.create_calls.append(body)
        return {"id": "provider-1", **body}

    async def cloudflare_health(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {"status": "ok", "provider": "cloudflare"}


@dataclass
class _StubBrokers:
    control_plane: _StubControlPlane
    monolith: _StubMonolith


def _patch_brokers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    should_fail_patch: bool = False,
) -> _StubBrokers:
    from aqp_admin.api.routers import settings as settings_router

    stub = _StubBrokers(
        control_plane=_StubControlPlane(should_fail_patch=should_fail_patch),
        monolith=_StubMonolith(),
    )
    monkeypatch.setattr(settings_router, "get_brokers", lambda: stub)
    return stub


def test_get_framework_settings_and_cloud_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_brokers(monkeypatch)

    framework = client.get("/admin/settings/framework", params={"service_id": "aqp-admin"})
    assert framework.status_code == 200
    framework_body = framework.json()
    assert framework_body["service_id"] == "aqp-admin"
    assert framework_body["persisted_config"]["values"]["AQP_ADMIN_API_URL"] == "http://localhost:8900"

    cloud = client.get("/admin/settings/cloud/status")
    assert cloud.status_code == 200
    cloud_body = cloud.json()
    assert len(cloud_body["terraform_providers"]) == 2
    assert cloud_body["control_plane_health"]["provider"] == "kubernetes"
    assert cloud_body["cloudflare_health"]["status"] == "ok"


def test_patch_framework_and_connect_provider_and_cloudflare(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _patch_brokers(monkeypatch)

    patch_response = client.patch(
        "/admin/settings/framework",
        json={
            "service_id": "aqp-admin",
            "namespace": "aqp",
            "values": {"AQP_ADMIN_AUTH_PROVIDER": "entra"},
            "delete_keys": [],
            "trigger_restart": True,
        },
    )
    assert patch_response.status_code == 200
    patch_body = patch_response.json()
    assert patch_body["service_id"] == "aqp-admin"
    assert patch_body["audit_run_id"] is not None
    assert stub.control_plane.patch_calls[0]["namespace"] == "aqp"

    provider_response = client.post(
        "/admin/settings/cloud/providers",
        json={
            "provider_kind": "aws",
            "slug": "aws-prod",
            "name": "AWS prod",
            "default_region": "us-east-1",
            "credential_key": "idp:aws:prod",
            "config_json": {"environment": "production"},
        },
    )
    assert provider_response.status_code == 200
    provider_body = provider_response.json()
    assert provider_body["provider"]["kind"] == "aws"
    assert provider_body["audit_run_id"] is not None

    cloudflare_response = client.post(
        "/admin/settings/cloud/cloudflare",
        json={
            "service_id": "aqp-admin",
            "namespace": "aqp",
            "account_id": "cf-account",
            "zone_id": "cf-zone",
            "team_domain": "team.cloudflareaccess.com",
            "trigger_restart": False,
        },
    )
    assert cloudflare_response.status_code == 200
    cloudflare_body = cloudflare_response.json()
    assert cloudflare_body["cloudflare_health"]["status"] == "ok"
    assert cloudflare_body["audit_run_id"] is not None


def test_patch_framework_maps_broker_failure_to_http(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_brokers(monkeypatch, should_fail_patch=True)

    response = client.patch(
        "/admin/settings/framework",
        json={
            "service_id": "aqp-admin",
            "values": {"AQP_ADMIN_AUDIT_SINK": "http"},
            "delete_keys": [],
            "trigger_restart": True,
        },
    )
    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["error"] == "upstream_unreachable"
