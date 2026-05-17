"""``data.rl.*`` MCP tools — RL experiment + run inspection.

Read-only browsing over ``rl_experiment_specs`` + ``rl_experiment_versions``
+ ``rl_runs`` so :class:`aqp.agents.quant.StrategyExecutor` (and any
other AgentSpec) can list / describe RL specs and the runs they
have produced without bypassing the DataMCP boundary (rule 22).

Tools provided:

- ``data.rl.experiments.list`` — list registered specs filtered by
  status / kind.
- ``data.rl.experiments.describe`` — describe one spec including its
  current_version hash for replay.
- ``data.rl.runs.list`` — list runs filtered by spec slug / status /
  target (train/evaluate/paper/replay/walk_forward).
- ``data.rl.runs.describe`` — describe a single run including
  metrics + checkpoint pointer.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models_rl import (
    RLExperimentSpec as RLSpecRow,
    RLExperimentVersion as RLVersionRow,
    RLRun,
)


def _spec_row_to_dict(row: RLSpecRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "slug": row.slug,
        "kind": row.kind,
        "description": row.description,
        "current_version": row.current_version,
        "status": row.status,
        "annotations": list(row.annotations or []),
        "project_id": getattr(row, "project_id", None),
        "workspace_id": getattr(row, "workspace_id", None),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_row_to_dict(row: RLRun) -> dict[str, Any]:
    return {
        "id": row.id,
        "spec_id": row.spec_id,
        "version_id": row.version_id,
        "target": row.target,
        "task_id": row.task_id,
        "status": row.status,
        "mlflow_run_id": row.mlflow_run_id,
        "checkpoint": row.checkpoint,
        "mean_reward": row.mean_reward,
        "total_reward": row.total_reward,
        "sharpe": row.sharpe,
        "max_drawdown": row.max_drawdown,
        "final_value": row.final_value,
        "total_return": row.total_return,
        "result_summary": dict(row.result_summary or {}),
        "error": row.error,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "experiment_id": getattr(row, "experiment_id", None),
    }


# ---------------------------------------------------------------------------
# data.rl.experiments.list
# ---------------------------------------------------------------------------


class ListRLExperimentsInput(BaseModel):
    status: str | None = Field(
        default=None, description="Filter by status (draft/active/archived)."
    )
    kind: str | None = Field(
        default=None, description="Filter by kind (training/evaluation/paper/...)."
    )
    project_id: str | None = Field(
        default=None, description="Filter by project_id. Defaults to context."
    )
    limit: int = Field(default=100, ge=1, le=500)


@register_data_mcp_tool
class ListRLExperimentsTool(DataMCPTool):
    name = "data.rl.experiments.list"
    description = (
        "List registered RL experiment specs (the latest active version of each "
        "named spec inside a project). Use before calling RLRuntime to discover "
        "which experiments exist."
    )
    args_schema = ListRLExperimentsInput
    category = "rl"
    tags = ("rl", "experiments", "list")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        status: str | None = None,
        kind: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        proj = project_id or ctx.project_id
        with get_session() as session:
            stmt = select(RLSpecRow)
            if status:
                stmt = stmt.where(RLSpecRow.status == status)
            if kind:
                stmt = stmt.where(RLSpecRow.kind == kind)
            if proj:
                stmt = stmt.where(RLSpecRow.project_id == proj)
            stmt = stmt.order_by(RLSpecRow.updated_at.desc()).limit(int(limit))
            items = [_spec_row_to_dict(r) for r in session.execute(stmt).scalars()]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} rl experiments",
        )


# ---------------------------------------------------------------------------
# data.rl.experiments.describe
# ---------------------------------------------------------------------------


class DescribeRLExperimentInput(BaseModel):
    slug: str = Field(description="Spec slug.")
    project_id: str | None = Field(
        default=None, description="Project scope. Defaults to context."
    )
    include_payload: bool = Field(
        default=False,
        description="Include the full hash-locked snapshot payload (large).",
    )


@register_data_mcp_tool
class DescribeRLExperimentTool(DataMCPTool):
    name = "data.rl.experiments.describe"
    description = (
        "Describe a single RL experiment spec, including the current "
        "spec_hash for deterministic replay. Pass include_payload=true "
        "to return the full immutable version snapshot."
    )
    args_schema = DescribeRLExperimentInput
    category = "rl"
    tags = ("rl", "experiments", "describe")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        slug: str,
        project_id: str | None = None,
        include_payload: bool = False,
    ) -> MCPToolResult:
        proj = project_id or ctx.project_id
        with get_session() as session:
            stmt = select(RLSpecRow).where(RLSpecRow.slug == slug)
            if proj:
                stmt = stmt.where(RLSpecRow.project_id == proj)
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:
                return MCPToolResult(ok=False, error=f"rl experiment {slug!r} not found")
            out = _spec_row_to_dict(row)
            version_payload: dict[str, Any] | None = None
            if include_payload:
                vstmt = (
                    select(RLVersionRow)
                    .where(RLVersionRow.spec_id == row.id)
                    .order_by(RLVersionRow.version.desc())
                    .limit(1)
                )
                vrow = session.execute(vstmt).scalar_one_or_none()
                if vrow is not None:
                    version_payload = {
                        "id": vrow.id,
                        "version": vrow.version,
                        "spec_hash": vrow.spec_hash,
                        "payload": dict(vrow.payload or {}),
                        "notes": vrow.notes,
                        "created_by": vrow.created_by,
                        "created_at": vrow.created_at.isoformat() if vrow.created_at else None,
                    }
            return MCPToolResult(
                ok=True,
                data={"experiment": out, "latest_version": version_payload},
                summary=f"rl experiment {slug}",
            )


# ---------------------------------------------------------------------------
# data.rl.runs.list
# ---------------------------------------------------------------------------


class ListRLRunsInput(BaseModel):
    spec_slug: str | None = Field(
        default=None, description="Filter by spec slug (resolves to spec_id)."
    )
    target: str | None = Field(
        default=None,
        description="Filter by target (train/evaluate/paper/replay/walk_forward).",
    )
    status: str | None = Field(default=None, description="Filter by status.")
    experiment_id: str | None = Field(
        default=None, description="Filter by experiment umbrella id (rule 34)."
    )
    limit: int = Field(default=50, ge=1, le=500)


@register_data_mcp_tool
class ListRLRunsTool(DataMCPTool):
    name = "data.rl.runs.list"
    description = (
        "List recent RL runs (train/evaluate/paper/replay/walk_forward) "
        "with optional filters on spec slug, target, status, or umbrella experiment id."
    )
    args_schema = ListRLRunsInput
    category = "rl"
    tags = ("rl", "runs", "list")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        spec_slug: str | None = None,
        target: str | None = None,
        status: str | None = None,
        experiment_id: str | None = None,
        limit: int = 50,
    ) -> MCPToolResult:
        with get_session() as session:
            spec_id: str | None = None
            if spec_slug:
                spec_stmt = select(RLSpecRow.id).where(RLSpecRow.slug == spec_slug)
                if ctx.project_id:
                    spec_stmt = spec_stmt.where(RLSpecRow.project_id == ctx.project_id)
                spec_id = session.execute(spec_stmt).scalar_one_or_none()
                if spec_id is None:
                    return MCPToolResult(
                        ok=False,
                        error=f"no rl experiment with slug={spec_slug!r}",
                    )
            stmt = select(RLRun)
            if spec_id:
                stmt = stmt.where(RLRun.spec_id == spec_id)
            if target:
                stmt = stmt.where(RLRun.target == target)
            if status:
                stmt = stmt.where(RLRun.status == status)
            if experiment_id:
                stmt = stmt.where(RLRun.experiment_id == experiment_id)
            stmt = stmt.order_by(RLRun.started_at.desc()).limit(int(limit))
            items = [_run_row_to_dict(r) for r in session.execute(stmt).scalars()]
        return MCPToolResult(
            ok=True,
            data={"items": items},
            rows_returned=len(items),
            summary=f"{len(items)} rl runs",
        )


# ---------------------------------------------------------------------------
# data.rl.runs.describe
# ---------------------------------------------------------------------------


class DescribeRLRunInput(BaseModel):
    run_id: str = Field(description="Run id (PK of rl_runs).")


@register_data_mcp_tool
class DescribeRLRunTool(DataMCPTool):
    name = "data.rl.runs.describe"
    description = "Describe one rl_runs row in detail (metrics + checkpoint + error)."
    args_schema = DescribeRLRunInput
    category = "rl"
    tags = ("rl", "runs", "describe")

    def run(self, *, ctx: MCPToolContext, run_id: str) -> MCPToolResult:
        with get_session() as session:
            row = session.get(RLRun, run_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"rl run {run_id!r} not found")
            payload = _run_row_to_dict(row)
            return MCPToolResult(
                ok=True,
                data=payload,
                summary=f"rl run {payload.get('id')}",
            )


__all__ = [
    "DescribeRLExperimentTool",
    "DescribeRLRunTool",
    "ListRLExperimentsTool",
    "ListRLRunsTool",
]
