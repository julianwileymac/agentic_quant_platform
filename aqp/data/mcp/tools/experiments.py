"""``data.experiments.*`` MCP tools — umbrella browsing for agents.

Read-only browsing over the Phase 1 ``experiments`` table so agents
can list / nest / describe user-driven experiments without bypassing
the DataMCP boundary.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models_experiments import Experiment


def _row_to_dict(row: Experiment) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "name": row.name,
        "kind": row.kind,
        "status": row.status,
        "parent_experiment_id": row.parent_experiment_id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "lab_id": row.lab_id,
        "owner_user_id": row.owner_user_id,
        "metrics": dict(row.metrics or {}),
        "tags": list(row.tags or []),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# data.experiments.list
# ---------------------------------------------------------------------------


class ListExperimentsInput(BaseModel):
    project_id: str | None = Field(
        default=None, description="Filter by project. Defaults to active context."
    )
    kind: str | None = Field(default=None, description="Filter by experiment kind.")
    status: str | None = Field(default=None, description="Filter by status.")
    parent_experiment_id: str | None = Field(
        default=None, description="Filter to direct children of an experiment."
    )
    limit: int = Field(default=100, ge=1, le=500)


@register_data_mcp_tool
class ListExperimentsTool(DataMCPTool):
    name = "data.experiments.list"
    description = (
        "List experiments visible in the active workspace/project, "
        "with optional filters on kind / status / parent."
    )
    args_schema = ListExperimentsInput
    category = "experiments"
    tags = ("experiments", "umbrella", "list")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_id: str | None = None,
        kind: str | None = None,
        status: str | None = None,
        parent_experiment_id: str | None = None,
        limit: int = 100,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(Experiment).order_by(Experiment.updated_at.desc()).limit(limit)
            target_project = project_id or ctx.project_id
            if target_project:
                query = query.where(Experiment.project_id == target_project)
            elif ctx.workspace_id:
                query = query.where(Experiment.workspace_id == ctx.workspace_id)
            if kind:
                query = query.where(Experiment.kind == kind)
            if status:
                query = query.where(Experiment.status == status)
            if parent_experiment_id:
                query = query.where(
                    Experiment.parent_experiment_id == parent_experiment_id
                )
            rows = session.execute(query).scalars().all()
            data = [_row_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"{len(data)} experiments",
        )


# ---------------------------------------------------------------------------
# data.experiments.tree
# ---------------------------------------------------------------------------


class ExperimentTreeInput(BaseModel):
    root_experiment_id: str = Field(..., description="Root experiment id.")
    depth: int = Field(default=3, ge=1, le=6)


@register_data_mcp_tool
class ExperimentTreeTool(DataMCPTool):
    name = "data.experiments.tree"
    description = (
        "Return the nested ``Experiment -> Experiment`` tree rooted at "
        "the given experiment, up to ``depth`` levels deep. Useful for "
        "rendering an ablation / sweep / hypothesis hierarchy."
    )
    args_schema = ExperimentTreeInput
    category = "experiments"
    tags = ("experiments", "tree", "nesting")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        root_experiment_id: str,
        depth: int = 3,
    ) -> MCPToolResult:
        tree: dict[str, Any] = {"id": root_experiment_id, "children": []}
        frontier = [(tree, root_experiment_id, 0)]
        nodes: dict[str, dict[str, Any]] = {}
        with get_session() as session:
            while frontier:
                parent_dict, exp_id, level = frontier.pop(0)
                row = session.get(Experiment, exp_id)
                if row is None:
                    continue
                payload = _row_to_dict(row)
                payload["children"] = []
                nodes[exp_id] = payload
                parent_dict.update(payload)
                if level >= depth:
                    continue
                children = (
                    session.execute(
                        select(Experiment).where(
                            Experiment.parent_experiment_id == exp_id
                        )
                    )
                    .scalars()
                    .all()
                )
                for child in children:
                    child_dict: dict[str, Any] = {"id": child.id, "children": []}
                    payload["children"].append(child_dict)
                    frontier.append((child_dict, child.id, level + 1))
        return MCPToolResult(
            ok=True,
            data=tree,
            rows_returned=len(nodes),
            summary=f"experiment tree rooted at {root_experiment_id} ({len(nodes)} nodes)",
        )


# ---------------------------------------------------------------------------
# data.experiments.describe
# ---------------------------------------------------------------------------


class DescribeExperimentInput(BaseModel):
    experiment_id: str = Field(...)


@register_data_mcp_tool
class DescribeExperimentTool(DataMCPTool):
    name = "data.experiments.describe"
    description = (
        "Return the full Experiment row with its metrics blob and a "
        "count of linked typed runs (backtest_runs, rl_runs, "
        "analysis_runs, bot_deployments, strategy_tests, paper_runs, "
        "ml_experiment_runs, agent_runs_v2)."
    )
    args_schema = DescribeExperimentInput
    category = "experiments"
    tags = ("experiments", "describe")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        experiment_id: str,
    ) -> MCPToolResult:
        # Defer imports — most callers don't need every run table.
        from aqp.persistence.models import (
            BacktestRun,
            MLExperimentRun,
            PaperTradingRun,
            StrategyTest,
        )
        from aqp.persistence.models_agents import AgentRunV2
        from aqp.persistence.models_analysis import AnalysisRun
        from aqp.persistence.models_bots import BotDeployment
        from aqp.persistence.models_rl import RLRun

        with get_session() as session:
            row = session.get(Experiment, experiment_id)
            if row is None:
                return MCPToolResult(
                    ok=False,
                    error=f"experiment {experiment_id!r} not found",
                    summary="describe miss",
                )
            data = _row_to_dict(row)
            counts: dict[str, int] = {}
            for label, model in (
                ("backtests", BacktestRun),
                ("ml_experiments", MLExperimentRun),
                ("rl_runs", RLRun),
                ("analysis_runs", AnalysisRun),
                ("bot_deployments", BotDeployment),
                ("strategy_tests", StrategyTest),
                ("paper_runs", PaperTradingRun),
                ("agent_runs", AgentRunV2),
            ):
                counts[label] = int(
                    session.query(model)
                    .filter(getattr(model, "experiment_id") == experiment_id)
                    .count()
                )
            data["run_counts"] = counts
        return MCPToolResult(
            ok=True,
            data=data,
            summary=f"described experiment {experiment_id}",
        )


__all__ = [
    "DescribeExperimentTool",
    "ExperimentTreeTool",
    "ListExperimentsTool",
]
