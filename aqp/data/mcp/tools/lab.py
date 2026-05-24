"""DataMCP tools backing the Data Lab (rule 22).

Exposes ``data.lab.{list_graphs, get_graph, list_runs, get_run,
list_artifacts, list_labels, list_notes, get_node_run}`` so agents
(including the ``agent.crewai`` Lab node) can introspect Lab graphs
and run history without bypassing the :class:`DataMCPTool` boundary.

Every tool is read-only, scoped to ``data:read``, and enforces tenancy
by filtering on ``ctx.workspace_id`` when present. Mutations against
``lab_*`` rows go through the FastAPI ``/lab/*`` router with explicit
write-scope checks + audit emits — they are *not* DataMCP tools.

The bridge in
:mod:`aqp.agents.tools.data_mcp_bridge` auto-installs every registered
:class:`DataMCPTool` into ``TOOL_REGISTRY``; the FastAPI router at
``/mcp/data`` and the ``aqp-data-mcp`` stdio binary surface the same
catalog externally.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models_lab import (
    LAB_LABEL_KINDS,
    LAB_MODES,
    LAB_NOTE_TARGETS,
    LabArtifact,
    LabGraph,
    LabLabel,
    LabNodeRun,
    LabNote,
    LabRun,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tenancy_filter(stmt: Any, ctx: MCPToolContext, *, model: Any) -> Any:
    """Append a workspace_id filter when the model + ctx both carry one."""
    if ctx.workspace_id and hasattr(model, "workspace_id"):
        stmt = stmt.where(model.workspace_id == ctx.workspace_id)
    return stmt


def _graph_to_dict(row: LabGraph) -> dict[str, Any]:
    return {
        "id": row.id,
        "lab_id": row.lab_id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "mode": row.mode,
        "content_hash": row.content_hash,
        "parent_graph_id": row.parent_graph_id,
        "data_snapshot": dict(row.data_snapshot or {}),
        "code_snapshot": row.code_snapshot,
        "archived_at": row.archived_at.isoformat() if row.archived_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_to_dict(row: LabRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "graph_id": row.graph_id,
        "lab_id": row.lab_id,
        "workspace_id": row.workspace_id,
        "experiment_id": row.experiment_id,
        "test_id": row.test_id,
        "mode": row.mode,
        "status": row.status,
        "content_hash": row.content_hash,
        "mlflow_run_id": row.mlflow_run_id,
        "workflow_run_id": row.workflow_run_id,
        "analysis_run_id": row.analysis_run_id,
        "rl_run_id": row.rl_run_id,
        "metrics": dict(row.metrics or {}),
        "result_summary": dict(row.result_summary or {}),
        "total_trials_searched": int(row.total_trials_searched or 1),
        "halted": bool(row.halted),
        "error": row.error,
        "duration_ms": row.duration_ms,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
    }


def _node_run_to_dict(row: LabNodeRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "node_id": row.node_id,
        "node_type": row.node_type,
        "status": row.status,
        "duration_ms": row.duration_ms,
        "output_locator": dict(row.output_locator or {}),
        "metrics": dict(row.metrics or {}),
        "error": row.error,
        "log_label": row.log_label,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
    }


def _artifact_to_dict(row: LabArtifact) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "node_id": row.node_id,
        "kind": row.kind,
        "uri": row.uri,
        "size_bytes": row.size_bytes,
        "content_hash": row.content_hash,
        "schema_json": dict(row.schema_json or {}),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _label_to_dict(row: LabLabel) -> dict[str, Any]:
    return {
        "id": row.id,
        "lab_id": row.lab_id,
        "vt_symbol": row.vt_symbol,
        "interval": row.interval,
        "t_start": row.t_start.isoformat() if row.t_start else None,
        "t_end": row.t_end.isoformat() if row.t_end else None,
        "kind": row.kind,
        "payload": dict(row.payload or {}),
        "run_id": row.run_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _note_to_dict(row: LabNote) -> dict[str, Any]:
    return {
        "id": row.id,
        "lab_id": row.lab_id,
        "target_kind": row.target_kind,
        "target_id": row.target_id,
        "body_md": row.body_md,
        "citations": list(row.citations or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# data.lab.list_graphs
# ---------------------------------------------------------------------------


class ListLabGraphsInput(BaseModel):
    lab_id: str | None = Field(default=None, description="Filter by lab id.")
    mode: str | None = Field(
        default=None,
        description=f"Filter by mode (one of {sorted(LAB_MODES)}).",
    )
    include_archived: bool = Field(default=False)
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class ListLabGraphsTool(DataMCPTool):
    name = "data.lab.list_graphs"
    description = (
        "List Data Lab GraphSpec rows, optionally filtered by lab id + "
        "mode. Returns metadata only (content_hash, mode, name, "
        "created_at, updated_at, archived_at) so the LLM can pick a "
        "graph to inspect deeper via data.lab.get_graph."
    )
    args_schema = ListLabGraphsInput
    category = "data_lab"
    tags = ("data_lab", "graphs", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        lab_id: str | None = None,
        mode: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
    ) -> MCPToolResult:
        if mode and mode not in LAB_MODES:
            return MCPToolResult(
                ok=False,
                error=f"unknown mode {mode!r}; valid: {sorted(LAB_MODES)}",
            )
        with get_session() as session:
            stmt = select(LabGraph)
            if lab_id:
                stmt = stmt.where(LabGraph.lab_id == lab_id)
            if mode:
                stmt = stmt.where(LabGraph.mode == mode)
            if not include_archived:
                stmt = stmt.where(LabGraph.archived_at.is_(None))
            stmt = _tenancy_filter(stmt, ctx, model=LabGraph)
            stmt = stmt.order_by(LabGraph.updated_at.desc()).limit(int(limit))
            rows = session.execute(stmt).scalars().all()
        items = [_graph_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"listed {len(items)} lab graphs",
        )


# ---------------------------------------------------------------------------
# data.lab.get_graph
# ---------------------------------------------------------------------------


class GetLabGraphInput(BaseModel):
    graph_id: str = Field(..., description="The LabGraph id.")
    include_spec: bool = Field(
        default=False,
        description="When true, also return the full GraphSpec JSON document.",
    )


@register_data_mcp_tool
class GetLabGraphTool(DataMCPTool):
    name = "data.lab.get_graph"
    description = (
        "Fetch a single Data Lab GraphSpec row by id. Optionally return "
        "the full nodes+edges JSON so the agent can reason about the "
        "graph topology. Use sparingly — the spec can be tens of KB."
    )
    args_schema = GetLabGraphInput
    category = "data_lab"
    tags = ("data_lab", "graphs", "get")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        graph_id: str,
        include_spec: bool = False,
    ) -> MCPToolResult:
        with get_session() as session:
            row = session.get(LabGraph, graph_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"graph {graph_id!r} not found")
            if (
                ctx.workspace_id
                and row.workspace_id
                and row.workspace_id != ctx.workspace_id
            ):
                return MCPToolResult(
                    ok=False, error="cross-tenant read denied"
                )
            payload = _graph_to_dict(row)
            if include_spec:
                payload["spec"] = dict(row.spec or {})
        return MCPToolResult(
            ok=True,
            data=payload,
            rows_returned=1,
            summary=f"graph {graph_id}",
        )


# ---------------------------------------------------------------------------
# data.lab.list_runs
# ---------------------------------------------------------------------------


class ListLabRunsInput(BaseModel):
    graph_id: str | None = Field(default=None)
    lab_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    mode: str | None = Field(default=None)
    experiment_id: str | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class ListLabRunsTool(DataMCPTool):
    name = "data.lab.list_runs"
    description = (
        "List LabRun ledger rows with optional filters by graph id, lab "
        "id, mode, status, or experiment id. Returns durations + metrics "
        "snapshot so the agent can prioritize which run to inspect."
    )
    args_schema = ListLabRunsInput
    category = "data_lab"
    tags = ("data_lab", "runs", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        graph_id: str | None = None,
        lab_id: str | None = None,
        status: str | None = None,
        mode: str | None = None,
        experiment_id: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        with get_session() as session:
            stmt = select(LabRun)
            if graph_id:
                stmt = stmt.where(LabRun.graph_id == graph_id)
            if lab_id:
                stmt = stmt.where(LabRun.lab_id == lab_id)
            if status:
                stmt = stmt.where(LabRun.status == status)
            if mode:
                stmt = stmt.where(LabRun.mode == mode)
            if experiment_id:
                stmt = stmt.where(LabRun.experiment_id == experiment_id)
            stmt = _tenancy_filter(stmt, ctx, model=LabRun)
            stmt = stmt.order_by(LabRun.started_at.desc()).limit(int(limit))
            rows = session.execute(stmt).scalars().all()
        items = [_run_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"listed {len(items)} lab runs",
        )


# ---------------------------------------------------------------------------
# data.lab.get_run
# ---------------------------------------------------------------------------


class GetLabRunInput(BaseModel):
    run_id: str = Field(..., description="The LabRun id.")


@register_data_mcp_tool
class GetLabRunTool(DataMCPTool):
    name = "data.lab.get_run"
    description = (
        "Fetch a single LabRun row by id with metrics, error, and "
        "soft-FK pointers (workflow_run_id, analysis_run_id, rl_run_id, "
        "mlflow_run_id) so the agent can cross-reference the runtime "
        "ledger it actually dispatched to."
    )
    args_schema = GetLabRunInput
    category = "data_lab"
    tags = ("data_lab", "runs", "get")

    def run(self, *, ctx: MCPToolContext, run_id: str) -> MCPToolResult:
        with get_session() as session:
            row = session.get(LabRun, run_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"run {run_id!r} not found")
            if (
                ctx.workspace_id
                and row.workspace_id
                and row.workspace_id != ctx.workspace_id
            ):
                return MCPToolResult(ok=False, error="cross-tenant read denied")
            payload = _run_to_dict(row)
        return MCPToolResult(
            ok=True,
            data=payload,
            rows_returned=1,
            summary=f"run {run_id}",
        )


# ---------------------------------------------------------------------------
# data.lab.list_node_runs
# ---------------------------------------------------------------------------


class ListLabNodeRunsInput(BaseModel):
    run_id: str = Field(..., description="The parent LabRun id.")
    status: str | None = Field(default=None)


@register_data_mcp_tool
class ListLabNodeRunsTool(DataMCPTool):
    name = "data.lab.list_node_runs"
    description = (
        "Return the per-node execution rows under a LabRun in the order "
        "they ran. Includes output_locator (URI pointer to the Arrow / "
        "Iceberg / MinIO artefact) and per-node metrics."
    )
    args_schema = ListLabNodeRunsInput
    category = "data_lab"
    tags = ("data_lab", "node_runs", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        run_id: str,
        status: str | None = None,
    ) -> MCPToolResult:
        with get_session() as session:
            parent = session.get(LabRun, run_id)
            if parent is None:
                return MCPToolResult(ok=False, error=f"run {run_id!r} not found")
            if (
                ctx.workspace_id
                and parent.workspace_id
                and parent.workspace_id != ctx.workspace_id
            ):
                return MCPToolResult(ok=False, error="cross-tenant read denied")
            stmt = select(LabNodeRun).where(LabNodeRun.run_id == run_id)
            if status:
                stmt = stmt.where(LabNodeRun.status == status)
            stmt = stmt.order_by(LabNodeRun.started_at.asc().nulls_first())
            rows = session.execute(stmt).scalars().all()
        items = [_node_run_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} node runs for run {run_id}",
        )


# ---------------------------------------------------------------------------
# data.lab.list_artifacts
# ---------------------------------------------------------------------------


class ListLabArtifactsInput(BaseModel):
    run_id: str = Field(..., description="The parent LabRun id.")
    kind: str | None = Field(default=None, description="Filter by artifact kind.")


@register_data_mcp_tool
class ListLabArtifactsTool(DataMCPTool):
    name = "data.lab.list_artifacts"
    description = (
        "List artefacts (Arrow tables, tearsheet HTML, MLflow registry "
        "URIs, Iceberg locators) produced by a LabRun. Optionally "
        "filtered by kind ('arrow', 'tearsheet', 'mlflow_model', ...)."
    )
    args_schema = ListLabArtifactsInput
    category = "data_lab"
    tags = ("data_lab", "artifacts", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        run_id: str,
        kind: str | None = None,
    ) -> MCPToolResult:
        with get_session() as session:
            parent = session.get(LabRun, run_id)
            if parent is None:
                return MCPToolResult(ok=False, error=f"run {run_id!r} not found")
            if (
                ctx.workspace_id
                and parent.workspace_id
                and parent.workspace_id != ctx.workspace_id
            ):
                return MCPToolResult(ok=False, error="cross-tenant read denied")
            stmt = select(LabArtifact).where(LabArtifact.run_id == run_id)
            if kind:
                stmt = stmt.where(LabArtifact.kind == kind)
            stmt = stmt.order_by(LabArtifact.created_at.asc())
            rows = session.execute(stmt).scalars().all()
        items = [_artifact_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} artifacts",
        )


# ---------------------------------------------------------------------------
# data.lab.list_labels
# ---------------------------------------------------------------------------


class ListLabLabelsInput(BaseModel):
    lab_id: str = Field(..., description="The lab id to list labels for.")
    vt_symbol: str | None = Field(default=None)
    kind: str | None = Field(
        default=None, description=f"Filter by label kind (one of {sorted(LAB_LABEL_KINDS)})."
    )
    limit: int = Field(default=500, ge=1, le=5000)


@register_data_mcp_tool
class ListLabLabelsTool(DataMCPTool):
    name = "data.lab.list_labels"
    description = (
        "List user-drawn chart annotations (support_resistance, "
        "trendline, swing, regime_band, pattern, order_event) attached "
        "to a lab. The 'Train labeler' wizard reads these as the "
        "supervised seed for label.triple_barrier / label.meta nodes."
    )
    args_schema = ListLabLabelsInput
    category = "data_lab"
    tags = ("data_lab", "labels", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        lab_id: str,
        vt_symbol: str | None = None,
        kind: str | None = None,
        limit: int = 500,
    ) -> MCPToolResult:
        if kind and kind not in LAB_LABEL_KINDS:
            return MCPToolResult(
                ok=False,
                error=f"unknown label kind {kind!r}; valid: {sorted(LAB_LABEL_KINDS)}",
            )
        with get_session() as session:
            stmt = select(LabLabel).where(LabLabel.lab_id == lab_id)
            if vt_symbol:
                stmt = stmt.where(LabLabel.vt_symbol == vt_symbol)
            if kind:
                stmt = stmt.where(LabLabel.kind == kind)
            stmt = _tenancy_filter(stmt, ctx, model=LabLabel)
            stmt = stmt.order_by(LabLabel.t_start.desc()).limit(int(limit))
            rows = session.execute(stmt).scalars().all()
        items = [_label_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} labels",
        )


# ---------------------------------------------------------------------------
# data.lab.list_notes
# ---------------------------------------------------------------------------


class ListLabNotesInput(BaseModel):
    lab_id: str = Field(..., description="The lab id to list notes for.")
    target_kind: str | None = Field(
        default=None,
        description=f"Filter by target kind (one of {sorted(LAB_NOTE_TARGETS)}).",
    )
    target_id: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)


@register_data_mcp_tool
class ListLabNotesTool(DataMCPTool):
    name = "data.lab.list_notes"
    description = (
        "List markdown notes attached to a graph / run / node_run / "
        "label / paper_chunk / snippet. agent.crewai nodes write notes "
        "here when they produce analysis output bound to a Lab artifact."
    )
    args_schema = ListLabNotesInput
    category = "data_lab"
    tags = ("data_lab", "notes", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        lab_id: str,
        target_kind: str | None = None,
        target_id: str | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        if target_kind and target_kind not in LAB_NOTE_TARGETS:
            return MCPToolResult(
                ok=False,
                error=f"unknown target_kind {target_kind!r}; valid: {sorted(LAB_NOTE_TARGETS)}",
            )
        with get_session() as session:
            stmt = select(LabNote).where(LabNote.lab_id == lab_id)
            if target_kind:
                stmt = stmt.where(LabNote.target_kind == target_kind)
            if target_id:
                stmt = stmt.where(LabNote.target_id == target_id)
            stmt = stmt.order_by(LabNote.created_at.desc()).limit(int(limit))
            rows = session.execute(stmt).scalars().all()
        items = [_note_to_dict(r) for r in rows]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} notes",
        )


__all__ = [
    "GetLabGraphTool",
    "GetLabRunTool",
    "ListLabArtifactsTool",
    "ListLabGraphsTool",
    "ListLabLabelsTool",
    "ListLabNodeRunsTool",
    "ListLabNotesTool",
    "ListLabRunsTool",
]
