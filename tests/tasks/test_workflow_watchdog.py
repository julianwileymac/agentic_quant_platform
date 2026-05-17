"""Phase 6 — workflow watchdog tests.

Covers:

- ``scan_for_stalled_workflow_runs`` task module exports the expected
  surface (mirrors ``test_watchdog.py::test_watchdog_task_module_exports``).
- Watchdog is no-op when
  ``orchestration_kill_propagation_enabled`` is False.
- When enabled and the ORM is reachable, stalled rows get marked
  ``status='halted'`` + ``halted=True``.
- :func:`collect_workflow_health_snapshot` returns the documented
  empty payload when the Phase 5 alembic migration hasn't applied.
"""
from __future__ import annotations

import pytest


def test_workflow_watchdog_module_exports():
    from aqp.tasks import agent_watchdog_tasks

    assert hasattr(agent_watchdog_tasks, "scan_for_stalled_workflow_runs")
    assert hasattr(agent_watchdog_tasks, "collect_workflow_health_snapshot")
    assert hasattr(agent_watchdog_tasks, "_scan_and_halt_workflow_runs")


def test_workflow_watchdog_noop_when_flag_off(monkeypatch):
    from aqp.config import settings as cfg
    from aqp.tasks import agent_watchdog_tasks as awd

    monkeypatch.setattr(
        cfg, "orchestration_kill_propagation_enabled", False, raising=True
    )
    out = awd._scan_and_halt_workflow_runs()
    assert out == []


def test_workflow_watchdog_noop_when_orm_missing(monkeypatch):
    """Even with the flag on, missing ORM degrades silently."""
    from aqp.config import settings as cfg
    from aqp.tasks import agent_watchdog_tasks as awd

    monkeypatch.setattr(
        cfg, "orchestration_kill_propagation_enabled", True, raising=True
    )

    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("table not provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    out = awd._scan_and_halt_workflow_runs()
    assert out == []


def test_workflow_health_snapshot_degrades_cleanly(monkeypatch):
    """Without the Phase 5 ORM the snapshot returns zeros + table_present=False."""
    import builtins

    real_import = builtins.__import__

    def _block(name, *args, **kwargs):
        if name == "aqp.persistence.models_workflows":
            raise ImportError("table not provisioned")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block)
    from aqp.tasks.agent_watchdog_tasks import collect_workflow_health_snapshot

    snap = collect_workflow_health_snapshot()
    assert snap["running"] == 0
    assert snap["pending"] == 0
    assert snap["halted_last_24h"] == 0
    assert snap["stalled_candidates"] == []
    assert snap["table_present"] is False


def test_workflow_watchdog_halt_marks_row(monkeypatch):
    """When the ORM is importable + flag on, a stalled fake row is halted.

    We exercise the helper that mutates a single row directly so we
    don't need a live Postgres for the assertion to hold.
    """
    from datetime import datetime, timedelta

    from aqp.tasks import agent_watchdog_tasks as awd

    class _FakeRow:
        id = "fake-run-1"
        task_id = "fake-task-1"
        status = "running"
        halted = False
        error = None
        completed_at = None
        workflow_spec_name = "fake.spec"

    monkeypatch.setattr(awd, "_revoke_celery_task", lambda task_id: True)
    row = _FakeRow()
    entry = awd._halt_workflow_row(row, reason="watchdog:test")
    assert entry["run_id"] == "fake-run-1"
    assert entry["task_id"] == "fake-task-1"
    assert entry["workflow_spec_name"] == "fake.spec"
    assert entry["revoked"] is True
    assert row.status == "halted"
    assert row.halted is True
    assert row.error == "watchdog:test"
    assert row.completed_at is not None


def test_scan_for_stalled_workflow_runs_celery_task_returns_payload(monkeypatch):
    """The Celery task wrapper returns the canonical ``{ok, halted_count}`` shape."""
    from aqp.tasks import agent_watchdog_tasks as awd

    monkeypatch.setattr(awd, "_scan_and_halt_workflow_runs", lambda: [{"x": 1}])

    result = awd._scan_for_stalled_workflow_runs_impl("test-task")
    assert result["ok"] is True
    assert result["halted_count"] == 1
    assert result["halted"] == [{"x": 1}]
