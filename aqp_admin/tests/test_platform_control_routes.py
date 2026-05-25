"""Admin platform-control routes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _admin_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AQP_ADMIN_AUTH_REQUIRED", "false")
    monkeypatch.setenv("AQP_ADMIN_AUDIT_SINK", "http")
    monkeypatch.delenv("AQP_ADMIN_AUDIT_HTTP_URL", raising=False)
    from aqp_admin.audit.sink import reset_audit_sink
    from aqp_admin.settings import reset_settings_cache

    reset_settings_cache()
    reset_audit_sink()


@pytest.fixture()
def client(_admin_test_env: None) -> TestClient:
    from aqp_admin.main import create_app

    return TestClient(create_app())


@dataclass
class _StubControlPlane:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def terraform_run(
        self,
        workspace_id: str,
        action: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": "terraform_run",
                "workspace_id": workspace_id,
                "action": action,
                "body": body,
                "bearer": bearer_passthrough,
            }
        )
        return {"status": "ok", "data": {"workspace_id": workspace_id, "action": action}}

    async def restart_deployment(
        self,
        service_id: str,
        *,
        namespace: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": "restart_deployment",
                "service_id": service_id,
                "namespace": namespace,
                "bearer": bearer_passthrough,
            }
        )
        return {"status": "ok", "data": {"service_id": service_id, "phase": "restarting"}}

    async def list_deployments(self, namespace: str | None = None) -> dict[str, Any]:
        return {
            "status": "ok",
            "data": [
                {
                    "service_id": "api",
                    "namespace": "tenant-acme",
                    "phase": "Running",
                    "replicas_desired": 2,
                    "replicas_ready": 2,
                }
            ],
        }


@dataclass
class _StubMonolith:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def list_terraform_workspaces(
        self,
        *,
        environment: str | None = None,
        archived: bool = False,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {
            "items": [
                {
                    "id": "ws-1",
                    "slug": "prod",
                    "environment": environment or "prod",
                    "archived": archived,
                }
            ],
            "total": 1,
        }

    async def cluster_status(
        self,
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        return {"adapter": "in_cluster", "status": "ok"}

    async def list_pods(
        self,
        namespace: str,
        *,
        label_selector: str | None = None,
        bearer_passthrough: str | None = None,
    ) -> list[dict[str, Any]]:
        return [{"name": "api-0", "namespace": namespace, "phase": "Running"}]

    async def exec_in_pod(
        self,
        namespace: str,
        name: str,
        body: dict[str, Any],
        *,
        bearer_passthrough: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": "exec_in_pod",
                "namespace": namespace,
                "name": name,
                "body": body,
                "bearer": bearer_passthrough,
            }
        )
        return {"stdout": "ok", "stderr": "", "exit_code": 0}


@dataclass
class _StubBrokers:
    control_plane: _StubControlPlane = field(default_factory=_StubControlPlane)
    monolith: _StubMonolith = field(default_factory=_StubMonolith)


def _patch_brokers(monkeypatch: pytest.MonkeyPatch) -> _StubBrokers:
    from aqp_admin.api.routers import kubernetes, services, terraform

    stub = _StubBrokers()
    monkeypatch.setattr(terraform, "get_brokers", lambda: stub)
    monkeypatch.setattr(kubernetes, "get_brokers", lambda: stub)
    monkeypatch.setattr(services, "get_brokers", lambda: stub)
    return stub


def test_terraform_metadata_and_control_plane_run(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _patch_brokers(monkeypatch)

    workspaces = client.get("/admin/terraform/workspaces")
    assert workspaces.status_code == 200
    assert workspaces.json()["items"][0]["id"] == "ws-1"

    response = client.post(
        "/admin/terraform/workspaces/ws-1/plan",
        headers={"Authorization": "Bearer user-token"},
        json={"spec": {"stack_name": "prod", "workspace_id": "ws-1"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["audit_run_id"] is not None
    assert stub.control_plane.calls[0]["action"] == "plan"
    assert stub.control_plane.calls[0]["bearer"] == "user-token"


def test_services_and_kubernetes_routes_are_brokered(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _patch_brokers(monkeypatch)

    service = client.post(
        "/admin/services/api/restart",
        json={"namespace": "tenant-acme"},
    )
    assert service.status_code == 200
    assert service.json()["audit_run_id"] is not None
    assert stub.control_plane.calls[0]["method"] == "restart_deployment"

    namespaces = client.get("/admin/kubernetes/namespaces")
    assert namespaces.status_code == 200
    assert namespaces.json()["namespaces"][0]["namespace"] == "tenant-acme"

    pods = client.get("/admin/kubernetes/pods/tenant-acme")
    assert pods.status_code == 200
    assert pods.json()["pods"][0]["name"] == "api-0"

    exec_response = client.post(
        "/admin/kubernetes/pods/tenant-acme/api-0/exec",
        json={"command": ["python", "--version"]},
    )
    assert exec_response.status_code == 200
    assert exec_response.json()["audit_run_id"] is not None
    assert stub.monolith.calls[0]["method"] == "exec_in_pod"
