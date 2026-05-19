"""End-to-end router smoke tests.

Auth is disabled (no AQP_AUTH_OIDC_ISSUER set) so the anonymous
synthesised user with admin:cluster handles everything. Provider
calls are routed at a stub provider that records what was invoked,
so we can verify the routers wire up + the audit ledger writes
without needing a real docker/k8s/cloud target.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aqp_cp.main import create_app
from aqp_cp.providers import bootstrap, get_provider_registry
from aqp_cp.settings import reset_settings_cache
from aqp_platform_core.models.config import ConfigMapPatch, ServiceConfig
from aqp_platform_core.models.deployment import (
    DeploymentLifecyclePhase,
    DeploymentSpec,
    DeploymentStatus,
)
from aqp_platform_core.models.health import HealthStatus, ProviderHealth
from aqp_platform_core.models.telemetry import MetricPoint
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    ProviderKind,
)


class _StubProvider(InfrastructureProvider):
    """Capture-all stub that records calls + returns deterministic data."""

    provider_kind = ProviderKind.DOCKER_COMPOSE
    provider_alias = "stub_provider"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def health(self) -> ProviderHealth:
        self.calls.append(("health", {}))
        return ProviderHealth(
            provider=self.provider_alias,
            status=HealthStatus.OK,
            available=True,
            last_probe_at=datetime.now(timezone.utc),
        )

    async def start(self, spec: DeploymentSpec) -> DeploymentStatus:
        self.calls.append(("start", {"service_id": spec.service_id}))
        return DeploymentStatus(
            service_id=spec.service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
            replicas_desired=spec.replicas,
            replicas_ready=spec.replicas,
        )

    async def stop(self, service_id: str, *, namespace=None) -> DeploymentStatus:
        self.calls.append(("stop", {"service_id": service_id}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.STOPPED,
        )

    async def scale(
        self, service_id: str, replicas: int, *, namespace=None
    ) -> DeploymentStatus:
        self.calls.append(("scale", {"service_id": service_id, "replicas": replicas}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
            replicas_desired=replicas,
            replicas_ready=replicas,
        )

    async def status(self, service_id: str, *, namespace=None) -> DeploymentStatus:
        self.calls.append(("status", {"service_id": service_id}))
        return DeploymentStatus(
            service_id=service_id,
            provider=self.provider_alias,
            phase=DeploymentLifecyclePhase.RUNNING,
            replicas_desired=1,
            replicas_ready=1,
        )

    async def list_deployments(self, *, namespace=None) -> list[DeploymentStatus]:
        self.calls.append(("list_deployments", {"namespace": namespace}))
        return [
            DeploymentStatus(
                service_id="aqp-api",
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.RUNNING,
            ),
            DeploymentStatus(
                service_id="aqp-worker",
                provider=self.provider_alias,
                phase=DeploymentLifecyclePhase.RUNNING,
            ),
        ]

    async def get_config(self, service_id: str, *, namespace=None) -> ServiceConfig:
        self.calls.append(("get_config", {"service_id": service_id}))
        return ServiceConfig(service_id=service_id, values={"FOO": "bar"})

    async def apply_config(self, patch: ConfigMapPatch) -> bool:
        self.calls.append(("apply_config", {"service_id": patch.service_id, "n_values": len(patch.values)}))
        return True


@pytest.fixture(autouse=True)
def _install_stub_provider(monkeypatch: pytest.MonkeyPatch) -> _StubProvider:
    monkeypatch.delenv("AQP_AUTH_OIDC_ISSUER", raising=False)
    monkeypatch.setenv("AQP_CP_PROVIDER", "stub_provider")
    reset_settings_cache()

    bootstrap()
    stub = _StubProvider()
    registry = get_provider_registry()
    registry.register("stub_provider", _StubProvider, replace=True)
    registry.replace_instance("stub_provider", stub)
    return stub


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


class TestDeploymentsRouter:
    def test_list_returns_envelope(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.get("/manage/deployments")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        items = body["data"]
        assert len(items) == 2
        assert items[0]["service_id"] == "aqp-api"
        assert ("list_deployments", {"namespace": None}) in _install_stub_provider.calls

    def test_start_emits_audit(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        payload = {
            "service_id": "aqp-api",
            "image": "ghcr.io/x:dev",
            "replicas": 2,
        }
        response = client.post("/manage/deployments/aqp-api/start", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["service_id"] == "aqp-api"
        assert body["data"]["phase"] == "running"
        assert any(c[0] == "start" for c in _install_stub_provider.calls)

    def test_scale_changes_replicas(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.patch("/manage/deployments/aqp-worker/scale?replicas=5")
        assert response.status_code == 200
        assert response.json()["data"]["replicas_desired"] == 5
        assert ("scale", {"service_id": "aqp-worker", "replicas": 5}) in _install_stub_provider.calls

    def test_stop_returns_stopped(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.post("/manage/deployments/aqp-worker/stop")
        assert response.status_code == 200
        assert response.json()["data"]["phase"] == "stopped"


class TestConfigRouter:
    def test_get_returns_envelope(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.get("/manage/config/aqp-api")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["values"] == {"FOO": "bar"}

    def test_patch_applies(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.patch(
            "/manage/config/aqp-api",
            json={
                "service_id": "aqp-api",
                "values": {"NEW": "value", "ANOTHER": "thing"},
                "delete_keys": [],
                "secret_refs": [],
                "trigger_restart": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["applied"] is True
        applied = [c for c in _install_stub_provider.calls if c[0] == "apply_config"]
        assert applied
        assert applied[0][1]["n_values"] == 2


class TestTelemetryRouter:
    def test_snapshot_endpoint_responds(self, client: TestClient) -> None:
        response = client.get("/manage/telemetry/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["provider"] == "stub_provider"
        assert body["data"]["status"] == "ok"


class TestOpenApiSpec:
    def test_all_new_routes_documented(self, client: TestClient) -> None:
        response = client.get("/manage/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        paths = spec["paths"]
        # Spot-check every router registered.
        for required in (
            "/manage/health",
            "/manage/deployments",
            "/manage/deployments/{service_id}",
            "/manage/deployments/{service_id}/start",
            "/manage/deployments/{service_id}/stop",
            "/manage/deployments/{service_id}/scale",
            "/manage/config/{service_id}",
            "/manage/telemetry/snapshot",
            "/manage/secrets/rotate/{service_id}",
            "/manage/secrets/audit",
        ):
            assert required in paths, f"missing OpenAPI path: {required}"


class TestSecretsRouter:
    def test_rotate_returns_501_with_audit_run_id(
        self, client: TestClient, _install_stub_provider: _StubProvider
    ) -> None:
        response = client.post(
            "/manage/secrets/rotate/aqp-api?secret_name=db-password"
        )
        assert response.status_code == 501
        body = response.json()
        assert body["detail"]["error"] == "rotation_pending"
        assert body["detail"]["audit_run_id"]
