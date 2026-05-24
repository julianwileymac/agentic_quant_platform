"""Bridge canonical progress frames → typed Lab envelopes.

The :class:`LabRuntime` and every executor call into
:func:`aqp.tasks._progress.emit`, which publishes onto the existing
``aqp:task:<task_id>`` Redis pub/sub channel. The Data Lab WebSocket
route subscribes to that same channel and runs each frame through
:func:`fanout_progress_frame` to produce a typed
:class:`LabServerEnvelope`.

Why this layer exists:

- Per AGENTS rule 4 the canonical ``{task_id, stage, message,
  timestamp, **extras}`` frame shape is contract — we never rename
  the top-level keys.
- The React Flow UI wants typed envelopes keyed by ``kind`` so it can
  switch-statement-route into the right handler (run.status →
  status pill, run.partial → AG Grid, sim.tick → chart layer, …).
- Putting the projection on the server side means every consumer
  (Vite UI, future Theia extension, Slack notifier) sees the same
  envelope shape.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from aqp.lab.ws.protocol import (
    EdaCellResultEnvelope,
    LabServerEnvelope,
    RunArtifactEnvelope,
    RunLogEnvelope,
    RunMetricEnvelope,
    RunPartialEnvelope,
    RunStatusEnvelope,
    SimTickEnvelope,
    StreamMarketEnvelope,
)

logger = logging.getLogger(__name__)


LAB_NAMESPACE = "task"


def lab_channel_id(task_id: str) -> str:
    """Channel id used to subscribe via :func:`aqp.ws.broker.asubscribe`.

    Today this is just the task_id passed straight through — we reuse
    the canonical ``aqp:task:<task_id>`` namespace. The helper exists
    so a future migration to a dedicated ``aqp:lab:`` namespace is a
    one-line change.
    """
    return task_id


def _stage_to_state(stage: str) -> str:
    """Map a stage string into a NodeStatus-compatible state token."""
    stage = (stage or "").lower()
    if stage == "done":
        return "done"
    if stage in {"error", "node:error"}:
        return "error"
    if stage in {"start", "compiled", "node:start"}:
        return "running"
    if stage == "node:done":
        return "done"
    if stage in {"halt", "halted", "cancelled"}:
        return "halted"
    return "running"


def fanout_progress_frame(frame: dict[str, Any]) -> LabServerEnvelope | None:
    """Project a canonical progress frame into a typed Lab envelope.

    Returns ``None`` for frames the Data Lab does not consume (the
    caller can still forward them to other channels). Never raises —
    malformed frames degrade to ``None``.
    """
    if not isinstance(frame, dict):
        return None

    # Forward every extra (tags / context / per-frame extras) so the
    # canonical contract holds at the envelope boundary — only the
    # well-known top-level keys are projected into typed fields.
    _PROJECTED = {
        "task_id",
        "timestamp",
        "stage",
        "message",
        "run_id",
        "node_id",
        "schema",
        "rows",
        "uri",
        "artifact_uri",
        "artifact_kind",
        "level",
        "msg",
        "cell_id",
        "stale_ids",
        "render",
        "t_ns",
        "lob",
        "pnl",
        "pos",
        "signals",
        "topic",
        "payload",
        "metric_name",
        "metric_value",
        "name",
        "value",
        "graph_content_hash",
    }
    extras: dict[str, Any] = {k: v for k, v in frame.items() if k not in _PROJECTED}

    base_kwargs: dict[str, Any] = {
        "task_id": str(frame.get("task_id") or ""),
        "timestamp": float(frame.get("timestamp") or 0.0),
        "stage": str(frame.get("stage") or ""),
        "message": str(frame.get("message") or ""),
    }
    base_kwargs.update(extras)

    stage = (frame.get("stage") or "").lower()
    node_id = frame.get("node_id")
    run_id = frame.get("run_id")

    # ---- sim.tick (Phase 4)
    if stage == "sim.tick":
        try:
            return SimTickEnvelope(
                run_id=str(run_id or ""),
                t_ns=int(frame.get("t_ns") or 0),
                lob=frame.get("lob"),
                pnl=frame.get("pnl"),
                pos=frame.get("pos"),
                signals=frame.get("signals"),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            logger.debug("sim.tick frame projection failed", exc_info=True)
            return None

    # ---- stream.market (Phase 4 live bridge)
    if stage.startswith("stream."):
        try:
            return StreamMarketEnvelope(
                topic=str(frame.get("topic") or ""),
                payload=dict(frame.get("payload") or {}),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- eda.cell.result (Phase 1)
    if stage == "eda.cell.result":
        try:
            return EdaCellResultEnvelope(
                cell_id=str(frame.get("cell_id") or ""),
                stale_ids=list(frame.get("stale_ids") or []),
                render=dict(frame.get("render") or {}),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- run.metric (any non-empty 'metrics' extras)
    if stage == "run.metric" or "metric_name" in frame:
        try:
            return RunMetricEnvelope(
                run_id=str(run_id or ""),
                node_id=str(node_id or ""),
                name=str(frame.get("metric_name") or frame.get("name") or "metric"),
                value=frame.get("metric_value", frame.get("value")),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- run.log (explicit log frames)
    if stage in {"log", "node:log"}:
        try:
            return RunLogEnvelope(
                run_id=str(run_id or ""),
                node_id=str(node_id) if node_id else None,
                level=str(frame.get("level") or "info"),
                msg=str(frame.get("msg") or frame.get("message") or ""),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- run.partial (frame previews)
    if stage == "run.partial":
        try:
            return RunPartialEnvelope(
                run_id=str(run_id or ""),
                node_id=str(node_id or ""),
                schema_name=str(frame.get("schema") or "frame"),
                rows=list(frame.get("rows") or []),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- run.artifact
    if stage in {"run.artifact", "artifact"} or frame.get("artifact_uri"):
        try:
            return RunArtifactEnvelope(
                run_id=str(run_id or ""),
                node_id=str(node_id or ""),
                uri=str(frame.get("artifact_uri") or frame.get("uri") or ""),
                artifact_kind=str(frame.get("artifact_kind") or "unknown"),
                schema_json=frame.get("schema"),
                **base_kwargs,
            )
        except Exception:  # noqa: BLE001
            return None

    # ---- run.status (the most common case — every emit gets one)
    try:
        return RunStatusEnvelope(
            run_id=str(run_id or ""),
            node_id=str(node_id) if node_id else None,
            state=_stage_to_state(stage),
            content_hash=frame.get("graph_content_hash"),
            **base_kwargs,
        )
    except Exception:  # noqa: BLE001
        logger.debug("default run.status projection failed", exc_info=True)
        return None


async def iter_lab_envelopes(task_id: str) -> AsyncIterator[LabServerEnvelope]:
    """Async iterator of typed envelopes for a given run ``task_id``.

    Wraps :func:`aqp.ws.broker.asubscribe` and filters out frames the
    Data Lab does not consume. Used by the WS route.
    """
    from aqp.ws.broker import asubscribe

    async for frame in asubscribe(lab_channel_id(task_id), namespace=LAB_NAMESPACE):
        envelope = fanout_progress_frame(frame)
        if envelope is not None:
            yield envelope


# ---------------------------------------------------------------------------
# LiveBridge — Redpanda topics → /ws/lab/{session_id} stream.market frames
# ---------------------------------------------------------------------------


# Topic naming convention from the plan §15.
TOPIC_PREFIX_MARKET = "md."  # md.{venue}.{asset_class}.{symbol}.{kind}
TOPIC_PREFIX_EXEC = "exec."  # exec.{env}.{venue}.{strategy_id}.{kind}
TOPIC_PREFIX_POSITION = "pos."  # pos.{env}.{strategy_id}.snapshot
TOPIC_PREFIX_PNL = "pnl."  # pnl.{env}.{strategy_id}.tick


def classify_topic(topic: str) -> str:
    """Return the envelope ``stage`` for a given Redpanda topic.

    The frontend uses the stage to route into the Simulation panes
    (price / executions / inventory) without parsing the topic.
    """
    if topic.startswith(TOPIC_PREFIX_MARKET):
        return "stream.market"
    if topic.startswith(TOPIC_PREFIX_EXEC):
        return "stream.exec"
    if topic.startswith(TOPIC_PREFIX_POSITION):
        return "stream.position"
    if topic.startswith(TOPIC_PREFIX_PNL):
        return "stream.pnl"
    return "stream.other"


def live_bridge_envelope(
    topic: str,
    payload: dict[str, Any],
    *,
    task_id: str,
    timestamp: float,
) -> dict[str, Any]:
    """Build a Lab WS frame from a single Redpanda message.

    Returned dict matches the canonical
    ``{task_id, stage, message, timestamp, **extras}`` shape so the
    standard :func:`fanout_progress_frame` projector can lift it into
    the typed :class:`StreamMarketEnvelope` family.
    """
    stage = classify_topic(topic)
    return {
        "v": 1,
        "task_id": task_id,
        "stage": stage,
        "message": f"live:{topic}",
        "timestamp": timestamp,
        "topic": topic,
        "payload": dict(payload),
    }


__all__ = [
    "LAB_NAMESPACE",
    "TOPIC_PREFIX_EXEC",
    "TOPIC_PREFIX_MARKET",
    "TOPIC_PREFIX_PNL",
    "TOPIC_PREFIX_POSITION",
    "classify_topic",
    "fanout_progress_frame",
    "iter_lab_envelopes",
    "lab_channel_id",
    "live_bridge_envelope",
]
