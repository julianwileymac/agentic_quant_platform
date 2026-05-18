"""Smoke tests for ``/assistants/*`` REST routes.

Mirrors :mod:`tests.api.test_workflows_route` — exercises the
``settings.assistant_engine_enabled`` gating and the happy path on
``GET /assistants`` + ``POST /assistants`` + ``POST /assistants/{name}/messages``
using mocked Celery + registry boundaries.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aqp.api.routes.assistants import router
from aqp.assistants.registry import (
    add_assistant_spec,
    clear_assistant_registry,
)
from aqp.assistants.spec import AssistantSpec


@pytest.fixture
def client(monkeypatch) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    # AuthDeps default to a deterministic local user when the auth
    # backend isn't installed; force that path for the tests so we
    # don't have to mint JWTs.
    return TestClient(app)


@pytest.fixture
def enable_engine(monkeypatch) -> None:
    from aqp.config import settings

    monkeypatch.setattr(settings, "assistant_engine_enabled", True, raising=True)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_assistant_registry()


def test_routes_503_when_engine_disabled(client) -> None:
    res = client.get("/assistants")
    assert res.status_code == 503
    assert "assistant engine disabled" in res.json()["detail"]


def test_list_assistants_returns_registered(client, enable_engine) -> None:
    add_assistant_spec(
        AssistantSpec(
            name="t.alpha",
            mode="agent",
            agent_spec_name="codebase_assistant",
            description="alpha assistant",
        )
    )
    res = client.get("/assistants")
    assert res.status_code == 200
    body = res.json()
    names = [s["name"] for s in body]
    assert "t.alpha" in names


def test_get_assistant_404_on_unknown(client, enable_engine) -> None:
    res = client.get("/assistants/does-not-exist")
    assert res.status_code == 404


def test_create_assistant_validates_payload(client, enable_engine) -> None:
    bad = {"name": "broken", "mode": "agent"}  # missing agent_spec_name
    res = client.post("/assistants", json=bad)
    assert res.status_code == 400
    assert "invalid assistant spec" in res.json()["detail"]


def test_create_assistant_round_trip(client, enable_engine) -> None:
    payload = {
        "name": "t.created",
        "mode": "agent",
        "agent_spec_name": "codebase_assistant",
        "description": "created via API",
        "system_instructions": "hi",
    }
    res = client.post("/assistants", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "t.created"
    listed = client.get("/assistants").json()
    assert any(s["name"] == "t.created" for s in listed)


def test_send_message_dispatches_to_celery(client, enable_engine, monkeypatch) -> None:
    add_assistant_spec(
        AssistantSpec(
            name="t.msgs",
            mode="agent",
            agent_spec_name="codebase_assistant",
        )
    )
    captured: dict[str, Any] = {}

    class _AsyncResult:
        id = "task-xyz"

    def _fake_apply_async(*, kwargs: dict[str, Any]) -> _AsyncResult:
        captured["kwargs"] = kwargs
        return _AsyncResult()

    from aqp.tasks import assistant_tasks as at

    monkeypatch.setattr(at.run_assistant, "apply_async", _fake_apply_async)

    res = client.post(
        "/assistants/t.msgs/messages",
        json={"prompt": "hello", "inputs": {"foo": "bar"}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"] == "task-xyz"
    assert body["stream_url"] == "/assistants/stream/task-xyz"
    assert captured["kwargs"]["assistant_spec_name"] == "t.msgs"
    assert captured["kwargs"]["prompt"] == "hello"


def test_halt_returns_ok_when_no_runs(client, enable_engine) -> None:
    res = client.post("/assistants/halt", json={"reason": "test"})
    # Degrades cleanly when the table isn't provisioned: returns
    # halted_count=0 either way.
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["halted_count"] == 0


def test_skills_endpoint_open_to_disabled_engine(client) -> None:
    """``/assistants/skills`` is read-only and not gated by the flag."""
    res = client.get("/assistants/skills")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
