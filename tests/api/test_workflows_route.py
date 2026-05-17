"""Phase 5 — :mod:`aqp.api.routes.workflows` integration tests.

Covers the additive workflow studio HTTP surface:

- Every route returns 503 when ``orchestration_studio_enabled`` is off.
- ``GET /workflows`` lists in-memory specs once the flag is on.
- ``POST /workflows`` validates the payload + adds to the registry.
- ``GET /workflows/{name}`` returns the full payload.
- ``POST /workflows/{name}/run`` thin-wraps Celery (mocked) and
  returns a ``TaskAccepted``.
- ``POST /workflows/halt`` mirrors the five existing halt routes
  with the same JSON shape.

Tests use a sandboxed FastAPI app to avoid pulling in the whole
``aqp.api.main`` boot path.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqp.agents.orchestration.registry_specs import (
    add_workflow_spec,
    clear_workflow_registry,
)
from aqp.agents.orchestration.spec import WorkflowSpec
from aqp.api.routes.workflows import router


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    clear_workflow_registry()
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    clear_workflow_registry()


@pytest.fixture()
def enable_studio(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_studio_enabled", True, raising=True)


def test_routes_return_503_when_studio_flag_off(client):
    """Every route refuses cleanly when the flag is off."""
    for path in ("/workflows", "/workflows/whatever", "/workflows/runs"):
        res = client.get(path)
        assert res.status_code == 503, res.text
        assert "studio disabled" in res.text


def test_list_workflows_returns_registered_specs(client, enable_studio):
    add_workflow_spec(
        WorkflowSpec(
            name="test.workflow.alpha",
            adapter="LangGraphAdapter",
            description="alpha workflow",
        )
    )
    res = client.get("/workflows")
    assert res.status_code == 200, res.text
    body = res.json()
    names = {w["name"] for w in body}
    assert "test.workflow.alpha" in names


def test_get_workflow_returns_full_payload(client, enable_studio):
    add_workflow_spec(
        WorkflowSpec(name="test.workflow.beta", adapter="LangGraphAdapter")
    )
    res = client.get("/workflows/test.workflow.beta")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "test.workflow.beta"
    assert "payload" in body
    assert body["payload"]["adapter"] == "LangGraphAdapter"


def test_get_workflow_returns_404_for_unknown(client, enable_studio):
    res = client.get("/workflows/does-not-exist")
    assert res.status_code == 404


def test_create_workflow_persists_to_registry(client, enable_studio):
    payload = {
        "name": "test.workflow.created",
        "adapter": "LangGraphAdapter",
        "description": "created via API",
        "params": {"builder": "research"},
        "max_rounds": 1,
        "annotations": ["test"],
        "template_target": "research",
    }
    res = client.post("/workflows", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "test.workflow.created"
    # Also reachable via the list endpoint.
    listed = client.get("/workflows").json()
    assert any(w["name"] == "test.workflow.created" for w in listed)


def test_create_workflow_rejects_invalid_payload(client, enable_studio):
    res = client.post(
        "/workflows",
        json={"name": "broken", "adapter": "LangGraphAdapter", "max_rounds": 0},
    )
    assert res.status_code == 400


def test_run_workflow_returns_task_accepted(client, enable_studio, monkeypatch):
    add_workflow_spec(
        WorkflowSpec(name="test.workflow.runnable", adapter="LangGraphAdapter")
    )

    class _FakeResult:
        id = "celery-task-xyz"

    captured: dict[str, Any] = {}

    def _fake_apply_async(*, kwargs):
        captured["kwargs"] = dict(kwargs)
        return _FakeResult()

    import aqp.tasks.orchestration_tasks as ot

    monkeypatch.setattr(ot.run_workflow, "apply_async", _fake_apply_async)
    res = client.post(
        "/workflows/test.workflow.runnable/run",
        json={"spec_name": "test.workflow.runnable", "inputs": {"foo": "bar"}},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["task_id"] == "celery-task-xyz"
    assert captured["kwargs"]["spec_name"] == "test.workflow.runnable"
    assert captured["kwargs"]["inputs"] == {"foo": "bar"}


def test_replay_run_returns_task_accepted(client, enable_studio, monkeypatch):
    class _FakeResult:
        id = "celery-replay-id"

    def _fake_apply_async(*, kwargs):
        return _FakeResult()

    import aqp.tasks.orchestration_tasks as ot

    monkeypatch.setattr(ot.replay_run, "apply_async", _fake_apply_async)
    res = client.post("/workflows/runs/some-run-id/replay")
    assert res.status_code == 200, res.text
    assert res.json()["task_id"] == "celery-replay-id"


def test_halt_returns_zero_when_no_runs(client, enable_studio):
    """When workflow_runs is empty, halt returns ok=True / halted=[]."""
    res = client.post("/workflows/halt", json={"reason": "test"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["halted_count"] == 0
    assert body["halted"] == []


def test_main_api_includes_workflows_router():
    """`aqp.api.main` mounts the workflows router unconditionally."""
    from aqp.api import main as main_mod

    paths = {route.path for route in main_mod.app.routes if hasattr(route, "path")}
    # Routes registered through the included router carry the /workflows prefix.
    assert any(p.startswith("/workflows") for p in paths)
