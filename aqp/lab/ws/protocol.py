"""Typed Data Lab WebSocket envelopes.

Every server-to-client frame extends the canonical
``{task_id, stage, message, timestamp, **extras}`` shape required by
AGENTS rule 4 — we add a ``kind`` discriminator + a few well-known
extras so the React Flow consumer can route by ``kind`` instead of
regex-matching ``stage`` strings.

Pydantic models here are deliberately permissive (``model_config =
ConfigDict(extra='allow')``) so extra keys propagate end-to-end
without renaming.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


LAB_NAMESPACE = "task"  # we reuse the existing aqp:task:<task_id> channel


class NodeStatus(str, Enum):
    """Mirror of :data:`aqp.persistence.models_lab.LAB_NODE_STATUSES`."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CACHED = "cached"
    SKIPPED = "skipped"


# ---------------------------------------------------------------------------
# Server -> client envelopes (subclasses share the canonical contract)
# ---------------------------------------------------------------------------


class _LabBase(BaseModel):
    """Common fields on every Lab envelope."""

    model_config = ConfigDict(extra="allow", protected_namespaces=())
    v: int = 1
    task_id: str
    timestamp: float
    stage: str = ""
    message: str = ""


class RunStatusEnvelope(_LabBase):
    kind: Literal["run.status"] = "run.status"
    run_id: str
    node_id: str | None = None
    state: str
    content_hash: str | None = None


class RunMetricEnvelope(_LabBase):
    kind: Literal["run.metric"] = "run.metric"
    run_id: str
    node_id: str
    name: str
    value: Any


class RunLogEnvelope(_LabBase):
    kind: Literal["run.log"] = "run.log"
    run_id: str
    node_id: str | None = None
    level: Literal["debug", "info", "warning", "error"] = "info"
    msg: str = ""


class RunPartialEnvelope(_LabBase):
    kind: Literal["run.partial"] = "run.partial"
    run_id: str
    node_id: str
    schema_name: str = Field(default="frame", alias="schema")
    rows: list[list[Any]] = Field(default_factory=list)

    model_config = ConfigDict(
        extra="allow", populate_by_name=True, protected_namespaces=()
    )


class RunArtifactEnvelope(_LabBase):
    kind: Literal["run.artifact"] = "run.artifact"
    run_id: str
    node_id: str
    uri: str
    artifact_kind: str
    schema_payload: dict[str, Any] | None = Field(default=None, alias="schema")

    model_config = ConfigDict(
        extra="allow", populate_by_name=True, protected_namespaces=()
    )


class EdaCellResultEnvelope(_LabBase):
    kind: Literal["eda.cell.result"] = "eda.cell.result"
    cell_id: str
    stale_ids: list[str] = Field(default_factory=list)
    render: dict[str, Any] = Field(default_factory=dict)


class SimTickEnvelope(_LabBase):
    kind: Literal["sim.tick"] = "sim.tick"
    run_id: str
    t_ns: int = 0
    lob: dict[str, Any] | None = None
    pnl: float | None = None
    pos: float | None = None
    signals: dict[str, Any] | None = None


class StreamMarketEnvelope(_LabBase):
    kind: Literal["stream.market"] = "stream.market"
    topic: str
    payload: dict[str, Any] = Field(default_factory=dict)


LabServerEnvelope = Union[
    RunStatusEnvelope,
    RunMetricEnvelope,
    RunLogEnvelope,
    RunPartialEnvelope,
    RunArtifactEnvelope,
    EdaCellResultEnvelope,
    SimTickEnvelope,
    StreamMarketEnvelope,
]


# ---------------------------------------------------------------------------
# Client -> server envelopes (subscribe / unsubscribe / eda.exec / sim.command)
# ---------------------------------------------------------------------------


class SubscribeEnvelope(BaseModel):
    kind: Literal["subscribe"] = "subscribe"
    v: int = 1
    stream: Literal["run", "live"] = "run"
    id: str  # run_id (or live channel id)


class UnsubscribeEnvelope(BaseModel):
    kind: Literal["unsubscribe"] = "unsubscribe"
    v: int = 1
    stream: Literal["run", "live"] = "run"
    id: str


class EdaExecEnvelope(BaseModel):
    kind: Literal["eda.exec"] = "eda.exec"
    v: int = 1
    cell_id: str
    code: str


class SimCommandEnvelope(BaseModel):
    kind: Literal["sim.command"] = "sim.command"
    v: int = 1
    run_id: str
    cmd: Literal["pause", "resume", "step", "seed", "speed"]
    value: Any | None = None


LabClientEnvelope = Union[
    SubscribeEnvelope,
    UnsubscribeEnvelope,
    EdaExecEnvelope,
    SimCommandEnvelope,
]


LabEnvelope = Union[LabServerEnvelope, LabClientEnvelope]


LAB_ENVELOPE_KINDS: tuple[str, ...] = (
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
]
