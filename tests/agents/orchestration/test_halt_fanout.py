"""Phase 6 — halt fan-out + cooperative cancellation.

Covers:

- :class:`WorkflowRuntime` halts within 1s of a kill switch flip.
- The runtime emits a canonical
  ``emit_done(..., {"halted": True, "stage": "kill_switch"})`` frame
  (rule 4 frame shape).
- The KillSwitch frontend component lists ``/workflows/halt`` among
  its halt targets.
- :func:`aqp.agents.graph.conditions.should_halt` is the sole gate
  the runtime polls between transitions (sanity check via inspection).
- :func:`data.orchestration.health` MCP tool surfaces the
  Phase 6 watchdog snapshot.
"""
from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any

import pytest

from aqp.agents.orchestration import (
    AdapterContext,
    AdapterResult,
    OrchestrationAdapter,
    WorkflowRuntime,
    WorkflowSpec,
)


@pytest.fixture(autouse=True)
def _clean_kill_switch(monkeypatch):
    """Hermetic: every test starts with the kill switch off."""
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: False,
    )


class _CountingAdapter(OrchestrationAdapter):
    adapter_kind = "graph"
    adapter_alias = "halt_fanout_counting_adapter"

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: Any, context: AdapterContext) -> AdapterResult:
        self.calls += 1
        return AdapterResult(state=state, status="completed")


def test_runtime_halts_within_one_second_of_kill_switch(monkeypatch):
    """Flipping the kill switch BEFORE run() makes the runtime halt
    instantly with the canonical kill_switch breadcrumb.
    """
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: True,
    )
    spec = WorkflowSpec(
        name="halt.fanout.fast", adapter="halt_fanout_counting_adapter"
    )
    adapter = _CountingAdapter()
    start = time.perf_counter()
    result = WorkflowRuntime(spec, adapter=adapter).run()
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    assert result.halted is True
    assert result.status == AdapterResult.STATUS_HALTED
    assert adapter.calls == 0  # adapter never invoked
    # Canonical breadcrumb shape
    crumbs = result.state.get("adapter_breadcrumbs", [])
    assert any(b.get("node") == "kill_switch" for b in crumbs)


def test_runtime_emits_canonical_halt_progress_frame(monkeypatch):
    """When task_id is wired, the runtime emits a halt frame whose
    ``stage`` is ``kill_switch`` per the Phase 2 design.
    """
    monkeypatch.setattr(
        "aqp.agents.graph.conditions.has_kill_switch",
        lambda _state: True,
    )
    captured: list[tuple[str, Any]] = []

    def _fake_emit_done(task_id, payload, *_args, **_kwargs):
        captured.append((task_id, payload))

    monkeypatch.setattr("aqp.tasks._progress.emit_done", _fake_emit_done)
    spec = WorkflowSpec(
        name="halt.fanout.frame", adapter="halt_fanout_counting_adapter"
    )
    runtime = WorkflowRuntime(
        spec, adapter=_CountingAdapter(), task_id="task-test-halt"
    )
    runtime.run()
    assert captured, "runtime must emit a done frame on halt"
    task_id, payload = captured[-1]
    assert task_id == "task-test-halt"
    assert payload["stage"] == "kill_switch"
    assert payload["halted"] is True


def test_killswitch_component_includes_workflows_halt_path():
    """Inspect the React source to confirm /workflows/halt is wired."""
    src_path = (
        Path(__file__).resolve().parents[3]
        / "frontend"
        / "src"
        / "components"
        / "common"
        / "KillSwitch.tsx"
    )
    source = src_path.read_text(encoding="utf-8")
    assert "/workflows/halt" in source
    # Must reuse the existing ConfirmFrictionDialog rather than ship a sibling.
    assert "ConfirmFrictionDialog" in source


def test_workflow_runtime_uses_should_halt_predicate():
    """``WorkflowRuntime._is_halted`` must funnel through
    :func:`aqp.agents.graph.conditions.should_halt` so the kill-switch
    gate stays a single chokepoint.
    """
    from aqp.agents.orchestration.runtime import WorkflowRuntime as _Runtime

    source = inspect.getsource(_Runtime._is_halted)
    assert "should_halt" in source
    assert "aqp.agents.graph.conditions" in source


def test_data_orchestration_health_tool_registered():
    """The Phase 6 MCP health tool is registered."""
    from aqp.data.mcp.registry import DATA_MCP_TOOLS

    assert "data.orchestration.health" in DATA_MCP_TOOLS


def test_data_orchestration_health_invoke_degrades_cleanly(monkeypatch):
    """Tool returns ``ok=True`` with ``table_present=False`` when the
    Phase 5 ORM is missing — the studio dashboard never goes red on
    a cold install.
    """
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("not yet provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.orchestration.health")
    res = tool.invoke(
        ctx=MCPToolContext(actor="test", granted_scopes=("data:read",))
    )
    assert res.ok is True
    assert res.data["table_present"] is False
    assert res.data["running"] == 0


def test_celery_beat_has_workflow_watchdog():
    from aqp.tasks.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "workflow-stall-watchdog" in beat
    entry = beat["workflow-stall-watchdog"]
    assert (
        entry["task"]
        == "aqp.tasks.agent_watchdog_tasks.scan_for_stalled_workflow_runs"
    )
