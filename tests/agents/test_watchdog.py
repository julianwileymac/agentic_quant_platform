"""Tests for the Phase 5 agent stall watchdog.

Covers:

- ``data.agents.health`` MCP tool is registered and degrades cleanly
  to ``ok=False`` when the underlying watchdog import fails.
- The settings knobs land on the canonical Settings.
- The watchdog Celery task module is importable + lists the expected
  surface (``scan_for_stalled_agent_runs``, ``collect_health_snapshot``,
  ``_scan_and_halt``).
- The Celery beat schedule registers ``agent-stall-watchdog``.
- ``GET /agents/health`` route is mounted and returns the expected
  JSON shape.

The DB-driven halt path is exercised by the
``test_scan_and_halt_marks_row`` test which uses an in-process SQLite
session_scope; we monkeypatch the Celery revoke + emit_done helpers so
the test runs without a broker.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest


def test_data_agents_health_tool_registered():
    from aqp.data.mcp.registry import DATA_MCP_TOOLS

    assert "data.agents.health" in DATA_MCP_TOOLS


def test_settings_have_watchdog_knobs():
    from aqp.config import settings

    assert hasattr(settings, "agent_stall_threshold_seconds")
    assert hasattr(settings, "agent_watchdog_enabled")
    assert hasattr(settings, "agent_watchdog_period_seconds")


def test_watchdog_task_module_exports():
    from aqp.tasks import agent_watchdog_tasks

    assert hasattr(agent_watchdog_tasks, "scan_for_stalled_agent_runs")
    assert hasattr(agent_watchdog_tasks, "collect_health_snapshot")
    assert hasattr(agent_watchdog_tasks, "_scan_and_halt")


def test_celery_beat_schedule_contains_watchdog():
    from aqp.tasks.celery_app import celery_app

    beat = celery_app.conf.beat_schedule
    assert "agent-stall-watchdog" in beat
    entry = beat["agent-stall-watchdog"]
    assert entry["task"] == "aqp.tasks.agent_watchdog_tasks.scan_for_stalled_agent_runs"
    assert isinstance(entry["schedule"], (int, float))


def test_agents_health_route_returns_snapshot(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.api.routes.agent_health import router

    fake_snapshot = {
        "running": 1,
        "pending": 2,
        "halted_last_24h": 3,
        "stalled_candidates": [],
        "stall_threshold_seconds": 300,
        "last_watchdog_at": datetime.utcnow().isoformat(),
    }

    def _stub_collect():
        return fake_snapshot

    monkeypatch.setattr(
        "aqp.tasks.agent_watchdog_tasks.collect_health_snapshot",
        _stub_collect,
    )

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.get("/agents/health")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["running"] == 1
    assert body["pending"] == 2
    assert body["halted_last_24h"] == 3


def test_data_agents_health_invoke(monkeypatch):
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    fake_snapshot = {
        "running": 5,
        "pending": 1,
        "halted_last_24h": 0,
        "stalled_candidates": [
            {
                "run_id": "abc",
                "spec": "foo",
                "started_at": "2026-05-17T00:00:00",
                "task_id": None,
                "stalled_seconds": 999,
                "status": "running",
            }
        ],
        "stall_threshold_seconds": 300,
        "last_watchdog_at": "2026-05-17T00:01:00",
    }

    def _stub_collect():
        return fake_snapshot

    monkeypatch.setattr(
        "aqp.tasks.agent_watchdog_tasks.collect_health_snapshot",
        _stub_collect,
    )

    tool = get_data_mcp_tool("data.agents.health")
    res = tool.invoke(ctx=MCPToolContext(granted_scopes=("data:read",)))
    assert res.ok is True
    assert res.data["running"] == 5
    assert res.rows_returned == 1


def test_data_agents_health_requires_scope():
    from aqp.data.mcp.base import MCPToolContext
    from aqp.data.mcp.registry import get_data_mcp_tool

    tool = get_data_mcp_tool("data.agents.health")
    res = tool.invoke(ctx=MCPToolContext(granted_scopes=()))
    assert res.ok is False
    assert "policy" in (res.error or "").lower()


def test_scan_and_halt_marks_row(monkeypatch):
    """End-to-end watchdog halt against an in-memory SQLite session."""
    pytest.importorskip("sqlalchemy")
    from datetime import datetime as _dt

    captured: list[dict[str, Any]] = []
    revokes: list[str] = []

    def _fake_revoke(task_id, terminate=False, signal=None):  # noqa: ARG001
        if task_id:
            revokes.append(str(task_id))

    def _fake_emit_done(task_id, payload):
        captured.append({"task_id": task_id, "payload": payload})

    monkeypatch.setattr(
        "aqp.tasks.agent_watchdog_tasks.emit_done", _fake_emit_done
    )
    # Patch the celery control surface so revoke() is harmless.
    from aqp.tasks import agent_watchdog_tasks

    class _FakeControl:
        def revoke(self, task_id, terminate=False, signal=None):  # noqa: ARG002
            _fake_revoke(task_id, terminate=terminate, signal=signal)

    monkeypatch.setattr(
        agent_watchdog_tasks.celery_app, "control", _FakeControl()
    )

    # Force ``settings.agent_stall_threshold_seconds`` low so the
    # synthetic row immediately qualifies.
    from aqp.config import settings

    monkeypatch.setattr(settings, "agent_stall_threshold_seconds", 1, raising=False)
    monkeypatch.setattr(settings, "agent_watchdog_enabled", True, raising=False)

    # Wire a throwaway SQLite engine + session.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from aqp.persistence import db as persistence_db
    from aqp.persistence.models import Base as _Base  # noqa: F401  (registers metadata)
    from aqp.persistence.models_agents import AgentRunStep, AgentRunV2

    engine = create_engine("sqlite:///:memory:", future=True)
    # Create just the agent tables we touch — the watchdog needs both
    # AgentRunV2 (status flip) and AgentRunStep (last-step heartbeat).
    AgentRunV2.__table__.create(bind=engine)
    AgentRunStep.__table__.create(bind=engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    from contextlib import contextmanager

    @contextmanager
    def _fake_scope():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(persistence_db, "get_session", _fake_scope)

    with _fake_scope() as session:
        stale = AgentRunV2(
            id="stale-run-1",
            spec_name="example_spec",
            status="running",
            task_id="celery-task-id-1",
            started_at=_dt.utcnow() - timedelta(seconds=600),
        )
        session.add(stale)

    halted = agent_watchdog_tasks._scan_and_halt()
    assert len(halted) == 1
    assert halted[0]["run_id"] == "stale-run-1"
    assert halted[0]["reason"] == "watchdog:stalled"
    assert revokes == ["celery-task-id-1"]
    # Row should now be ``halted``.
    with _fake_scope() as session:
        row = session.query(AgentRunV2).filter_by(id="stale-run-1").one()
        assert row.status == "halted"
        assert row.error == "watchdog:stalled"
        assert row.completed_at is not None
    # emit_done frame was published.
    assert captured and captured[0]["payload"]["halted"] is True
