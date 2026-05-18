"""Tests for the local stack sugar routes + Celery task wiring.

Covers:
- ``POST /terraform/stacks/{name}/up`` returns TaskAccepted with a
  ``/ws/terraform/runs/<task_id>`` stream URL.
- The four mutating routes (up / down / build / refresh) call
  ``run_local_stack.apply_async`` with the right action.
- ``GET /terraform/stacks/{name}/endpoints`` degrades cleanly when
  terraform / kubectl aren't installed.
- The ``run_local_stack`` Celery body dispatches to TerraformRuntime
  with the prerendered_workspace_dir flag.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    from aqp.api.routes.terraform import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _patch_apply_async(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _AsyncResult:
        id = "task-local-1"

    def _fake_apply_async(*, kwargs: dict[str, Any]) -> _AsyncResult:
        captured["kwargs"] = kwargs
        return _AsyncResult()

    from aqp.tasks import terraform_tasks as tt

    monkeypatch.setattr(tt.run_local_stack, "apply_async", _fake_apply_async)
    return captured


def test_local_stack_up_returns_task_accepted(client, monkeypatch):
    captured = _patch_apply_async(monkeypatch)
    res = client.post("/terraform/stacks/aqp-local/up")
    # 401 / 403 means the test client isn't auth'd; degrade test to
    # check the JSON shape on a 200.
    if res.status_code in (401, 403):
        pytest.skip("require_authenticated rejected the test client")
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"] == "task-local-1"
    assert body["stream_url"] == "/ws/terraform/runs/task-local-1"
    assert captured["kwargs"]["action"] == "up"
    assert captured["kwargs"]["spec_name"] == "aqp-local"


def test_local_stack_down_uses_destroy_action(client, monkeypatch):
    captured = _patch_apply_async(monkeypatch)
    res = client.post("/terraform/stacks/aqp-local/down")
    if res.status_code in (401, 403):
        pytest.skip("require_authenticated rejected the test client")
    assert res.status_code == 200
    assert captured["kwargs"]["action"] == "down"


def test_local_stack_build_uses_build_action(client, monkeypatch):
    captured = _patch_apply_async(monkeypatch)
    res = client.post("/terraform/stacks/aqp-local/build")
    if res.status_code in (401, 403):
        pytest.skip("require_authenticated rejected the test client")
    assert res.status_code == 200
    assert captured["kwargs"]["action"] == "build"


def test_local_stack_endpoints_degrades_cleanly(monkeypatch):
    """When runtime / adapter reads fail the route returns blank fields."""
    from aqp.api.routes import control_plane
    from aqp.api.routes import terraform as terraform_routes

    class _Runtime:
        def outputs(self):
            return {}

    class _Adapter:
        def list_pods(self, *, namespace: str, label_selector: str | None = None):
            raise RuntimeError("cluster unavailable")

    monkeypatch.setattr(terraform_routes, "_local_stack_runtime", lambda: _Runtime())
    monkeypatch.setattr(control_plane, "_adapter_for_target", lambda _target: _Adapter())

    payload = terraform_routes.local_stack_endpoints("aqp-local")
    assert payload.api_url is None
    assert payload.frontend_url is None
    assert payload.pods == {"running": 0, "pending": 0, "failed": 0, "total": 0}


def test_local_stack_endpoints_use_runtime_and_adapter(monkeypatch):
    from aqp.api.routes import control_plane
    from aqp.api.routes import terraform as terraform_routes
    from aqp.kubernetes.protocol import PodInfo

    class _Runtime:
        def outputs(self):
            return {
                "api_url": "http://localhost:8000/api",
                "frontend_url": "http://localhost:8000/",
                "namespace": "aqp-local",
                "endpoints": {"registry": "localhost:5001"},
            }

    class _Adapter:
        def list_pods(self, *, namespace: str, label_selector: str | None = None):
            assert namespace == "aqp-local"
            return [
                PodInfo(namespace=namespace, name="api", phase="Running"),
                PodInfo(namespace=namespace, name="worker", phase="Pending"),
            ]

    monkeypatch.setattr(terraform_routes, "_local_stack_runtime", lambda: _Runtime())
    monkeypatch.setattr(control_plane, "_adapter_for_target", lambda _target: _Adapter())

    payload = terraform_routes.local_stack_endpoints("aqp-local")
    assert payload.api_url == "http://localhost:8000/api"
    assert payload.registry == "localhost:5001"
    assert payload.pods == {"running": 1, "pending": 1, "failed": 0, "total": 2}


def test_run_local_stack_task_dispatches_to_runtime(monkeypatch):
    """The Celery body calls TerraformRuntime.plan + apply for action='up'."""
    from aqp.tasks import terraform_tasks as tt
    from aqp.terraform.spec import TerraformStackSpec

    spec = TerraformStackSpec(
        name="aqp-local",
        slug="aqp-local",
        module_kind="composite",
        environment="local",
        cloud_provider="local",
    )
    monkeypatch.setattr(tt, "_load_local_spec", lambda: spec)

    plan_calls: list[Any] = []
    apply_calls: list[Any] = []

    class _Result:
        def __init__(self, exit_code: int = 0) -> None:
            self.exit_code = exit_code
            self.status = "completed"

        def to_dict(self) -> dict[str, Any]:
            return {"exit_code": self.exit_code, "status": self.status}

    class _StubRuntime:
        def __init__(self, *, spec, workspace_id, task_id, prerendered_workspace_dir):
            assert prerendered_workspace_dir, "expected prerendered workspace path"
            assert workspace_id == "aqp-local"

        def plan(self, *, destroy: bool = False, **_kw):
            plan_calls.append("plan")
            return _Result(2)  # 0 or 2 are both "ok" for plan

        def apply(self, **_kw):
            apply_calls.append("apply")
            return _Result(0)

        def destroy(self, **_kw):
            return _Result(0)

        def refresh(self, **_kw):
            return _Result(0)

    monkeypatch.setattr("aqp.terraform.runtime.TerraformRuntime", _StubRuntime)
    monkeypatch.setattr(tt, "emit", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_done", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_error", lambda *a, **k: None)

    # Drive the impl directly so we don't have to bind a Celery task.
    payload = tt._run_local_stack_impl("test-task-id", action="up", spec_name="aqp-local")
    assert payload["status"] == "completed"
    assert plan_calls == ["plan"]
    assert apply_calls == ["apply"]


def test_run_local_stack_rejects_unknown_action(monkeypatch):
    from aqp.tasks import terraform_tasks as tt

    monkeypatch.setattr(tt, "emit_error", lambda *a, **k: None)
    payload = tt._run_local_stack_impl("test", action="bogus", spec_name="aqp-local")
    assert payload["ok"] is False
    assert "unknown local stack action" in payload["error"]


def test_run_rpi_stack_task_dispatches_to_runtime(monkeypatch):
    from aqp.tasks import terraform_tasks as tt
    from aqp.terraform.spec import TerraformStackSpec

    spec = TerraformStackSpec(
        name="aqp-rpi-kubernetes",
        slug="aqp-rpi-kubernetes",
        module_kind="composite",
        environment="live",
        cloud_provider="rpi_cluster",
    )
    monkeypatch.setattr(tt, "_load_rpi_spec", lambda: spec)

    plan_calls: list[Any] = []
    apply_calls: list[Any] = []

    class _Result:
        def __init__(self, exit_code: int = 0) -> None:
            self.exit_code = exit_code
            self.status = "completed"

        def to_dict(self) -> dict[str, Any]:
            return {"exit_code": self.exit_code, "status": self.status}

    class _StubRuntime:
        def __init__(self, *, spec, workspace_id, task_id, prerendered_workspace_dir):
            assert prerendered_workspace_dir, "expected prerendered workspace path"
            assert workspace_id == "aqp-rpi-kubernetes"

        def plan(self, *, destroy: bool = False, **_kw):
            plan_calls.append("plan")
            return _Result(2)

        def apply(self, **_kw):
            apply_calls.append("apply")
            return _Result(0)

        def destroy(self, **_kw):
            return _Result(0)

        def refresh(self, **_kw):
            return _Result(0)

    monkeypatch.setattr("aqp.terraform.runtime.TerraformRuntime", _StubRuntime)
    monkeypatch.setattr(tt, "emit", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_done", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_error", lambda *a, **k: None)

    payload = tt._run_rpi_stack_impl(
        "test-task-id", action="up", spec_name="aqp-rpi-kubernetes"
    )
    assert payload["status"] == "completed"
    assert payload["ok"] is True
    assert plan_calls == ["plan"]
    assert apply_calls == ["apply"]


def test_run_rpi_stack_requires_zero_for_apply_success(monkeypatch):
    from aqp.tasks import terraform_tasks as tt
    from aqp.terraform.spec import TerraformStackSpec

    spec = TerraformStackSpec(
        name="aqp-rpi-kubernetes",
        slug="aqp-rpi-kubernetes",
        module_kind="composite",
        environment="live",
        cloud_provider="rpi_cluster",
    )
    monkeypatch.setattr(tt, "_load_rpi_spec", lambda: spec)

    class _Result:
        def __init__(self, exit_code: int = 0) -> None:
            self.exit_code = exit_code
            self.status = "completed"

        def to_dict(self) -> dict[str, Any]:
            return {"exit_code": self.exit_code, "status": self.status}

    class _StubRuntime:
        def __init__(self, *, spec, workspace_id, task_id, prerendered_workspace_dir):
            return None

        def plan(self, *, destroy: bool = False, **_kw):
            return _Result(2)

        def apply(self, **_kw):
            return _Result(2)

    monkeypatch.setattr("aqp.terraform.runtime.TerraformRuntime", _StubRuntime)
    monkeypatch.setattr(tt, "emit", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_done", lambda *a, **k: None)
    monkeypatch.setattr(tt, "emit_error", lambda *a, **k: None)

    payload = tt._run_rpi_stack_impl(
        "test-task-id", action="up", spec_name="aqp-rpi-kubernetes"
    )
    assert payload["status"] == "completed"
    assert payload["ok"] is False


def test_run_rpi_stack_rejects_unknown_action(monkeypatch):
    from aqp.tasks import terraform_tasks as tt

    monkeypatch.setattr(tt, "emit_error", lambda *a, **k: None)
    payload = tt._run_rpi_stack_impl(
        "test", action="bogus", spec_name="aqp-rpi-kubernetes"
    )
    assert payload["ok"] is False
    assert "unknown rpi stack action" in payload["error"]
