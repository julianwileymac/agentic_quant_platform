"""WS envelope projection tests."""
from __future__ import annotations

import time

from aqp.lab.ws import (
    LAB_ENVELOPE_KINDS,
    EdaCellResultEnvelope,
    NodeStatus,
    RunStatusEnvelope,
    fanout_progress_frame,
    lab_channel_id,
)


def test_lab_channel_id_passthrough() -> None:
    assert lab_channel_id("run-abc") == "run-abc"


def test_fanout_default_to_run_status() -> None:
    frame = {
        "task_id": "t-1",
        "stage": "start",
        "message": "starting",
        "timestamp": time.time(),
        "run_id": "r-1",
        "node_id": "n-1",
        "graph_content_hash": "abc123",
    }
    env = fanout_progress_frame(frame)
    assert isinstance(env, RunStatusEnvelope)
    assert env.state == "running"
    assert env.run_id == "r-1"
    assert env.node_id == "n-1"
    assert env.content_hash == "abc123"


def test_fanout_done_stage_projects_done_state() -> None:
    frame = {
        "task_id": "t-1",
        "stage": "node:done",
        "message": "ok",
        "timestamp": 1.0,
        "run_id": "r-1",
        "node_id": "n-2",
    }
    env = fanout_progress_frame(frame)
    assert isinstance(env, RunStatusEnvelope)
    assert env.state == "done"


def test_fanout_error_stage_projects_error_state() -> None:
    frame = {
        "task_id": "t-2",
        "stage": "error",
        "message": "boom",
        "timestamp": 1.0,
        "run_id": "r-1",
    }
    env = fanout_progress_frame(frame)
    assert isinstance(env, RunStatusEnvelope)
    assert env.state == "error"


def test_fanout_eda_cell_result_projection() -> None:
    frame = {
        "task_id": "t-3",
        "stage": "eda.cell.result",
        "message": "",
        "timestamp": 1.0,
        "cell_id": "c-99",
        "stale_ids": ["c-100"],
        "render": {"kind": "stub"},
    }
    env = fanout_progress_frame(frame)
    assert isinstance(env, EdaCellResultEnvelope)
    assert env.cell_id == "c-99"
    assert env.stale_ids == ["c-100"]


def test_fanout_returns_none_for_non_dict() -> None:
    assert fanout_progress_frame("nope") is None  # type: ignore[arg-type]
    assert fanout_progress_frame(None) is None  # type: ignore[arg-type]


def test_node_status_values_known() -> None:
    assert "done" in {s.value for s in NodeStatus}
    assert "running" in {s.value for s in NodeStatus}


def test_envelope_kinds_complete() -> None:
    expected = {
        "run.status",
        "run.metric",
        "run.log",
        "run.partial",
        "run.artifact",
        "eda.cell.result",
        "sim.tick",
        "stream.market",
        "subscribe",
        "unsubscribe",
        "eda.exec",
        "sim.command",
    }
    assert expected.issubset(set(LAB_ENVELOPE_KINDS))


def test_envelope_keeps_canonical_frame_keys() -> None:
    """AGENTS rule 4 — top-level keys task_id/stage/message/timestamp survive."""
    frame = {
        "task_id": "t-4",
        "stage": "start",
        "message": "hello",
        "timestamp": 123.456,
        "run_id": "r-5",
        "tags": {"workspace_id": "w-1"},
    }
    env = fanout_progress_frame(frame)
    payload = env.model_dump()
    assert payload["task_id"] == "t-4"
    assert payload["stage"] == "start"
    assert payload["message"] == "hello"
    assert payload["timestamp"] == 123.456
    # Extras (tags) pass through via extra='allow'
    assert payload.get("tags") == {"workspace_id": "w-1"}
