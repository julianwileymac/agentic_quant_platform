"""Data Lab WebSocket protocol + fanout helpers.

The Data Lab does NOT introduce a new pub/sub namespace. It reuses
the canonical ``aqp:task:<task_id>`` channel populated by
:func:`aqp.tasks._progress.emit`. The :mod:`aqp.lab.ws.fanout` module
projects those frames into typed Lab envelopes
(:mod:`aqp.lab.ws.protocol`) consumed by the React Flow UI.

This keeps AGENTS rule 4 intact — the canonical frame shape
``{task_id, stage, message, timestamp, **extras}`` is the source of
truth, and the Data Lab is a typed reader/writer of that shape.
"""
from __future__ import annotations

from aqp.lab.ws.fanout import (
    LAB_NAMESPACE,
    fanout_progress_frame,
    iter_lab_envelopes,
    lab_channel_id,
)
from aqp.lab.ws.protocol import (
    LAB_ENVELOPE_KINDS,
    EdaCellResultEnvelope,
    EdaExecEnvelope,
    LabClientEnvelope,
    LabEnvelope,
    LabServerEnvelope,
    NodeStatus,
    RunArtifactEnvelope,
    RunLogEnvelope,
    RunMetricEnvelope,
    RunPartialEnvelope,
    RunStatusEnvelope,
    SimCommandEnvelope,
    SimTickEnvelope,
    StreamMarketEnvelope,
    SubscribeEnvelope,
    UnsubscribeEnvelope,
)

__all__ = [
    "EdaCellResultEnvelope",
    "EdaExecEnvelope",
    "LAB_ENVELOPE_KINDS",
    "LAB_NAMESPACE",
    "LabClientEnvelope",
    "LabEnvelope",
    "LabServerEnvelope",
    "NodeStatus",
    "RunArtifactEnvelope",
    "RunLogEnvelope",
    "RunMetricEnvelope",
    "RunPartialEnvelope",
    "RunStatusEnvelope",
    "SimCommandEnvelope",
    "SimTickEnvelope",
    "StreamMarketEnvelope",
    "SubscribeEnvelope",
    "UnsubscribeEnvelope",
    "fanout_progress_frame",
    "iter_lab_envelopes",
    "lab_channel_id",
]
