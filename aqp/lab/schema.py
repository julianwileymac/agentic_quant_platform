"""Pydantic schema for the Data Lab GraphSpec.

``GraphSpec`` is the single document the React Flow shell submits.
:class:`aqp.lab.runtime.LabRuntime` then lowers it to one of four
existing execution targets (EDA cell preview, Celery canvas, Celery
sweep group, Dagster sandbox job) — see :mod:`aqp.lab.compiler`.

Design choices intentionally mirrored from
:class:`aqp.agents.orchestration.spec.WorkflowSpec`:

- The Pydantic models freeze on construction; mutation is rejected so
  the same in-memory instance is safely hashable.
- :meth:`GraphSpec.snapshot_hash` returns the canonical-JSON SHA256;
  every persistence row + WebSocket envelope references it.
- ``mode`` is one of ``eda``, ``testing``, ``evaluation``, ``simulation``
  (the four UI modes). The compile target is selected by this field
  alone — adapter dispatch is not the user's concern.

Port dtypes describe the typed wire between nodes. The compiler
performs structural validation (every required input is wired, every
edge dtype matches the upstream output) before dispatch.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PortDType(str, Enum):
    """Typed edge between two NodeSpecs.

    A subset of the dtypes maps onto wire frames the WebSocket can
    stream (``tick_stream``, ``bar_series``, ``orderbook_l2``,
    ``run.partial``). The rest are persisted-only handles (frame,
    panel, signal, weights, portfolio, model_artifact, ...).
    """

    TICK_STREAM = "tick_stream"
    BAR_SERIES = "bar_series"
    ORDERBOOK_L2 = "orderbook_l2"
    ORDERBOOK_L3 = "orderbook_l3"
    FRAME = "frame"
    PANEL = "panel"
    SIGNAL = "signal"
    WEIGHTS = "weights"
    PORTFOLIO = "portfolio"
    MODEL_ARTIFACT = "model_artifact"
    PARAMS = "params"
    SCALAR = "scalar"
    JSON = "json"
    ANNOTATION_SET = "annotation_set"
    RL_ENV = "rl_env"
    RL_POLICY = "rl_policy"
    AGENT_HANDLE = "agent_handle"


class Port(BaseModel):
    """One typed input or output socket on a node."""

    model_config = ConfigDict(frozen=True)

    name: str
    dtype: PortDType
    optional: bool = False
    description: str | None = None


class NodeRuntime(BaseModel):
    """How a node executes.

    ``target`` picks the executor family:

    - ``celery`` — Testing & Evaluation modes dispatch through Celery
      (one task per node by default).
    - ``dagster`` — Simulation mode runs inside the long-lived
      :class:`SandboxRuntime` job.
    - ``marimo_cell`` — EDA mode dispatches through
      :class:`AnalysisRuntime.preview` per cell.
    - ``inline`` — pure-function executors that the compiler can call
      synchronously (used by the EDA cell DAG).
    """

    model_config = ConfigDict(frozen=True)

    target: Literal["celery", "dagster", "marimo_cell", "inline"] = "celery"
    queue: str = "lab.default"
    image: str | None = None
    timeout_s: int = 300
    resources: dict[str, str] = Field(default_factory=dict)


class NodeSpec(BaseModel):
    """One node in a :class:`GraphSpec`.

    ``type`` is a registered :class:`aqp.lab.registry.NodeType` alias
    (e.g. ``alpha.formulaic``, ``strategy.vbt_portfolio``). ``inputs`` /
    ``outputs`` are typed Ports; ``params`` is validated by the
    NodeType's bundled Pydantic params model.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"n-{uuid4().hex[:10]}")
    type: str
    label: str = ""
    category: Literal[
        "DataSource",
        "Transformation",
        "Feature",
        "Alpha",
        "Model",
        "Strategy",
        "Math",
        "Labeler",
        "Output",
        "Agent",
    ]
    position: tuple[float, float] = (0.0, 0.0)
    inputs: list[Port] = Field(default_factory=list)
    outputs: list[Port] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    runtime: NodeRuntime = Field(default_factory=NodeRuntime)
    snapshot_inputs: bool = True
    notes: str | None = None

    @field_validator("id")
    @classmethod
    def _id_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("NodeSpec.id must be non-empty")
        return v.strip()


class EdgeSpec(BaseModel):
    """One typed edge between (source_node, output_port) → (target_node, input_port)."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"e-{uuid4().hex[:10]}")
    source: str
    target: str
    source_port: str = "out"
    target_port: str = "in"
    dtype: PortDType | None = None


class SweepConfig(BaseModel):
    """Evaluation mode — describes the parameter sweep.

    ``param_paths`` use dot syntax against ``GraphSpec.nodes[*].params``
    (e.g. ``alpha_formulaic.decay`` resolves to
    ``nodes[node_id='alpha_formulaic'].params['decay']``). ``values``
    are explicit grids; ``algo`` switches between grid / random /
    optuna_tpe / ray_tune_asha.
    """

    model_config = ConfigDict(frozen=True)

    algo: Literal["grid", "random", "optuna_tpe", "ray_tune_asha"] = "grid"
    primary_metric: str = "sharpe"
    maximize: bool = True
    budget: int = 16
    cv: Literal["holdout", "walk_forward", "combinatorial_purged"] = "holdout"
    cv_kwargs: dict[str, Any] = Field(default_factory=dict)
    param_paths: list[str] = Field(default_factory=list)
    values: dict[str, list[Any]] = Field(default_factory=dict)
    ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)
    seed: int = 42


class SimulationConfig(BaseModel):
    """Simulation mode — describes the runtime environment."""

    model_config = ConfigDict(frozen=True)

    env: Literal["hftbt", "stochastic", "rl", "optctl"] = "hftbt"
    seed: int = 42
    speed: float = 1.0
    capital: float = 1_000_000.0
    fee_bps: float = 1.0
    latency_ns: int = 250_000
    extras: dict[str, Any] = Field(default_factory=dict)


class EvalConfig(BaseModel):
    """Top-level wrapper consumed by the Evaluation compiler."""

    model_config = ConfigDict(frozen=True)

    sweep: SweepConfig = Field(default_factory=SweepConfig)


class EdaConfig(BaseModel):
    """Top-level wrapper consumed by the EDA compiler."""

    model_config = ConfigDict(frozen=True)

    cells: list["EdaCell"] = Field(default_factory=list)


class EdaCell(BaseModel):
    """One cell in the EDA notebook surface.

    Cells are NOT NodeSpecs — the EDA mode has a separate, lighter
    weight reactive cell DAG. A cell's content is either Python or
    SQL; references between cells form the DAG.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: f"c-{uuid4().hex[:10]}")
    kind: Literal["python", "sql", "markdown", "chart"] = "python"
    source: str = ""
    ord: int = 0


class ModeConfig(BaseModel):
    """Per-mode runtime configuration carried on the GraphSpec.

    Only one branch is populated at any given time (the one matching
    ``GraphSpec.mode``). The compiler asserts the relationship.
    """

    model_config = ConfigDict(frozen=True)

    eda: EdaConfig | None = None
    testing: dict[str, Any] | None = None
    evaluation: EvalConfig | None = None
    simulation: SimulationConfig | None = None


class GraphSpec(BaseModel):
    """The Data Lab's single source-of-truth graph document.

    The reproducibility contract is ``(content_hash, data_snapshot,
    code_snapshot)`` — every ``lab_runs`` row carries the triple.
    """

    model_config = ConfigDict(frozen=True)

    name: str = "untitled"
    description: str = ""
    mode: Literal["eda", "testing", "evaluation", "simulation"] = "testing"
    nodes: list[NodeSpec] = Field(default_factory=list)
    edges: list[EdgeSpec] = Field(default_factory=list)
    mode_config: ModeConfig = Field(default_factory=ModeConfig)
    parent_graph_id: str | None = None
    annotations: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------ helpers

    def snapshot_hash(self) -> str:
        """SHA256 of canonical-JSON dump (sorted keys, no whitespace).

        Mirrors :meth:`WorkflowSpec.snapshot_hash`. See
        :mod:`aqp.lab.hashing` for the helper used everywhere else.
        """
        from aqp.lab.hashing import compute_content_hash

        return compute_content_hash(self)

    @model_validator(mode="after")
    def _validate_edges_reference_nodes(self) -> "GraphSpec":
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(
                    f"EdgeSpec {edge.id!r} references unknown source {edge.source!r}"
                )
            if edge.target not in node_ids:
                raise ValueError(
                    f"EdgeSpec {edge.id!r} references unknown target {edge.target!r}"
                )
        return self

    @model_validator(mode="after")
    def _validate_mode_config_branch(self) -> "GraphSpec":
        mc = self.mode_config
        active = {
            "eda": mc.eda is not None,
            "testing": mc.testing is not None,
            "evaluation": mc.evaluation is not None,
            "simulation": mc.simulation is not None,
        }
        # We allow the mode_config to be entirely empty (defaults will
        # apply on the compile target). We only complain if the user
        # set a config branch that doesn't match ``mode``.
        for branch, present in active.items():
            if present and branch != self.mode:
                raise ValueError(
                    f"mode_config.{branch} is set but GraphSpec.mode={self.mode!r}"
                )
        return self

    def topological_order(self) -> list[NodeSpec]:
        """Return nodes in topological order; raise on cycles.

        Implementation: Kahn's algorithm. Used by the Testing /
        Evaluation compilers. Pure helper — no side effects.
        """
        adj: dict[str, list[str]] = {n.id: [] for n in self.nodes}
        indeg: dict[str, int] = {n.id: 0 for n in self.nodes}
        for edge in self.edges:
            adj[edge.source].append(edge.target)
            indeg[edge.target] += 1
        ready = [nid for nid, d in indeg.items() if d == 0]
        order: list[str] = []
        while ready:
            ready.sort()  # deterministic for tests
            cur = ready.pop(0)
            order.append(cur)
            for nxt in adj.get(cur, []):
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    ready.append(nxt)
        if len(order) != len(self.nodes):
            raise ValueError("GraphSpec contains a cycle; topological sort failed")
        by_id = {n.id: n for n in self.nodes}
        return [by_id[nid] for nid in order]


EdaConfig.model_rebuild()


__all__ = [
    "EdaCell",
    "EdaConfig",
    "EdgeSpec",
    "EvalConfig",
    "GraphSpec",
    "ModeConfig",
    "NodeRuntime",
    "NodeSpec",
    "Port",
    "PortDType",
    "SimulationConfig",
    "SweepConfig",
]
