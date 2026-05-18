"""``aqp.tasks.assistant_tasks.run_assistant`` Celery wrapper tests.

Drives ``_run_assistant_impl`` directly so we can verify the task
hydrates the spec by name, threads the ``RequestContext`` through to
the runtime, and emits a clean ``emit_error`` when the spec lookup
misses (rather than crashing the worker).
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.assistants.registry import (
    add_assistant_spec,
    clear_assistant_registry,
)
from aqp.assistants.spec import AssistantSpec
from aqp.tasks.assistant_tasks import _run_assistant_impl


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_assistant_registry()


def test_run_assistant_impl_resolves_spec_by_name(monkeypatch):
    add_assistant_spec(
        AssistantSpec(
            name="t.run",
            mode="agent",
            agent_spec_name="codebase_assistant",
        )
    )

    captured: dict[str, Any] = {}

    class _StubRuntime:
        def __init__(self, spec, **kwargs):
            captured["spec_name"] = spec.name
            captured["kwargs"] = kwargs

        def run(self, *, prompt, inputs):
            captured["prompt"] = prompt
            captured["inputs"] = dict(inputs)
            return {"status": "completed", "output": {"text": "ok"}}

    monkeypatch.setattr(
        "aqp.assistants.runtime.AssistantRuntime", _StubRuntime, raising=False
    )
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit_done", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit_error", lambda *a, **k: None
    )

    payload = _run_assistant_impl(
        "task-1",
        assistant_spec_name="t.run",
        prompt="hi",
        inputs={"prompt": "hi"},
    )
    assert payload["status"] == "completed"
    assert captured["spec_name"] == "t.run"
    assert captured["prompt"] == "hi"


def test_run_assistant_impl_emits_error_for_missing_spec(monkeypatch):
    captured: dict[str, Any] = {}

    def _record_error(task_id, msg, **_extra):
        captured["task_id"] = task_id
        captured["msg"] = msg

    monkeypatch.setattr("aqp.tasks.assistant_tasks.emit", lambda *a, **k: None)
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit_error", _record_error
    )

    out = _run_assistant_impl("task-2", assistant_spec_name="missing")
    assert out["ok"] is False
    assert "missing" in (out.get("error") or "")
    assert captured["msg"].startswith("no spec resolvable")


def test_run_assistant_impl_binds_request_context(monkeypatch):
    add_assistant_spec(
        AssistantSpec(
            name="t.ctx",
            mode="agent",
            agent_spec_name="codebase_assistant",
        )
    )

    bound: dict[str, Any] = {}

    class _StubRuntime:
        def __init__(self, spec, *, context=None, **_kw):
            bound["context"] = context

        def run(self, *, prompt, inputs):
            return {"status": "completed", "output": {}}

    monkeypatch.setattr(
        "aqp.assistants.runtime.AssistantRuntime", _StubRuntime, raising=False
    )
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "aqp.tasks.assistant_tasks.emit_done", lambda *a, **k: None
    )

    out = _run_assistant_impl(
        "task-3",
        assistant_spec_name="t.ctx",
        prompt="hi",
        context={"user_id": "alice", "workspace_id": "ws-1"},
    )
    assert out["status"] == "completed"
    assert bound["context"] is not None
