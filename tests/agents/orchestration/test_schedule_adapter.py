"""Phase 3 — :class:`AutomationScheduleAdapter` tests.

Covers:

- Adapter refuses to enqueue when
  ``settings.orchestration_schedule_enabled`` is ``False``.
- When enabled, ``invoke`` enqueues
  ``aqp.tasks.orchestration_tasks.run_workflow.apply_async`` with the
  right keyword arguments and stamps ``schedule_metadata`` on the
  state.
- :func:`register_schedule_with_celery_beat` mounts a workflow on
  ``celery_app.conf.beat_schedule`` under a ``workflow-<slug>`` key.
- The schedule adapter NEVER imports ORM models or DataMCP tools
  directly — keeps rule 22 + rule 5 intact.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from aqp.agents.orchestration import AdapterContext, AdapterResult, WorkflowSpec
from aqp.agents.orchestration.adapters.schedule_adapter import (
    AutomationScheduleAdapter,
    beat_key_for_spec,
    register_schedule_with_celery_beat,
)


def _ctx(**overrides) -> AdapterContext:
    return AdapterContext(
        workflow_run_id="rid-parent",
        workflow_spec_name="research.daily_stock_analysis_v1",
        request_id="req",
        extras={
            "params": {
                "target_spec_name": "research.daily_stock_analysis_v1",
                "target_spec_version_id": "ver-xyz",
                "inputs": {"foo": "bar"},
                "countdown_seconds": 0,
            },
            **overrides.pop("extras", {}),
        },
        **overrides,
    )


def test_adapter_refuses_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_schedule_enabled", False, raising=True)
    adapter = AutomationScheduleAdapter()
    result = adapter.invoke({}, _ctx())
    assert result.status == AdapterResult.STATUS_ERROR
    assert result.failure is not None
    assert result.failure.kind == "policy"


def test_adapter_enqueues_run_workflow_when_flag_on(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_schedule_enabled", True, raising=True)

    captured = {}

    class _FakeResult:
        id = "celery-task-123"

    def _fake_apply_async(*, kwargs, countdown):
        captured["kwargs"] = dict(kwargs)
        captured["countdown"] = countdown
        return _FakeResult()

    import aqp.tasks.orchestration_tasks as ot

    monkeypatch.setattr(ot.run_workflow, "apply_async", _fake_apply_async)

    adapter = AutomationScheduleAdapter()
    state = {"adapter_breadcrumbs": []}
    result = adapter.invoke(state, _ctx())
    assert result.status == AdapterResult.STATUS_COMPLETED
    assert captured["countdown"] == 0
    assert captured["kwargs"]["spec_name"] == "research.daily_stock_analysis_v1"
    assert captured["kwargs"]["spec_version_id"] == "ver-xyz"
    assert captured["kwargs"]["inputs"] == {"foo": "bar"}
    assert captured["kwargs"]["parent_run_id"] == "rid-parent"
    # State carries the schedule metadata + breadcrumb.
    meta = result.state["schedule_metadata"]
    assert meta["celery_task_id"] == "celery-task-123"
    assert meta["parent_run_id"] == "rid-parent"
    crumbs = result.state["adapter_breadcrumbs"]
    assert crumbs and crumbs[-1]["status"] == "ok"
    assert crumbs[-1]["adapter"] == "AutomationScheduleAdapter"


def test_adapter_respects_halt_check(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_schedule_enabled", True, raising=True)
    adapter = AutomationScheduleAdapter()
    ctx = AdapterContext(
        workflow_run_id="rid",
        workflow_spec_name="spec",
        request_id="req",
        halt_check=lambda: True,
    )
    result = adapter.invoke({}, ctx)
    assert result.status == AdapterResult.STATUS_HALTED


def test_register_schedule_noop_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg

    monkeypatch.setattr(cfg, "orchestration_schedule_enabled", False, raising=True)
    spec = WorkflowSpec(
        name="research.scheduled_v1",
        adapter="LangGraphAdapter",
    )
    key = register_schedule_with_celery_beat(spec, interval_seconds=60)
    assert key is None


def test_register_schedule_writes_beat_entry(monkeypatch):
    from aqp.config import settings as cfg
    from aqp.tasks.celery_app import celery_app

    monkeypatch.setattr(cfg, "orchestration_schedule_enabled", True, raising=True)
    monkeypatch.setattr(celery_app.conf, "beat_schedule", {})
    spec = WorkflowSpec(
        name="research.scheduled_v1",
        adapter="LangGraphAdapter",
    )
    key = register_schedule_with_celery_beat(spec, interval_seconds=120)
    assert key == "workflow-research-scheduled-v1"
    entry = celery_app.conf.beat_schedule[key]
    assert entry["task"] == "aqp.tasks.orchestration_tasks.run_workflow"
    assert entry["schedule"] == 120.0
    assert entry["kwargs"]["spec_name"] == "research.scheduled_v1"


def test_beat_key_for_spec_slugifies():
    assert beat_key_for_spec("research.daily.v1") == "workflow-research-daily-v1"
    assert beat_key_for_spec("complicated/name with spaces!") == (
        "workflow-complicated-name-with-spaces"
    )


def test_schedule_adapter_does_not_import_orm():
    """Rule 22: adapter source must NOT reference aqp.persistence.models_*."""
    source = inspect.getsource(
        __import__(
            "aqp.agents.orchestration.adapters.schedule_adapter",
            fromlist=["__file__"],
        )
    )
    assert "aqp.persistence.models" not in source
    assert "iceberg_catalog" not in source


def test_orchestration_tasks_module_does_not_import_orm_at_top_level():
    """Rule from tasks-api.mdc: no top-level ORM imports in task modules."""
    src_path = (
        Path(__file__).resolve().parents[3]
        / "aqp"
        / "tasks"
        / "orchestration_tasks.py"
    )
    source = src_path.read_text(encoding="utf-8")
    # Strip everything inside def bodies to find module-top imports only.
    head_lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            break
        head_lines.append(line)
    head = "\n".join(head_lines)
    assert "aqp.persistence.models" not in head
    assert "iceberg_catalog" not in head


def test_run_workflow_task_emits_clean_error_when_spec_missing(monkeypatch):
    """When neither spec_version_id nor spec_name resolve, the task
    emits a structured error frame and returns ``ok=False``."""
    import aqp.tasks.orchestration_tasks as ot

    captured_errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ot,
        "emit_error",
        lambda task_id, msg, **_: captured_errors.append((task_id, msg)),
    )
    monkeypatch.setattr(ot, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(ot, "emit_done", lambda *args, **kwargs: None)

    # Use the testable impl helper so we don't wrestle with
    # Celery's ``bind=True`` descriptor in unit tests.
    result = ot._run_workflow_impl(
        "test-task-id", spec_version_id=None, spec_name=None
    )
    assert result["ok"] is False
    assert captured_errors  # emit_error fired


@pytest.mark.parametrize("alias", ["LangGraphAdapter", "AutomationScheduleAdapter"])
def test_adapter_classes_register_through_metaclass(alias):
    """Sanity check that the Phase 3 adapter joins the registry."""
    from aqp.agents.orchestration.registry import get_adapter

    cls = get_adapter(alias)
    assert cls is not None
