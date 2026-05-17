"""Pipeline DataMCP tools.

Read-only browse of :class:`PipelineManifestRow` and :class:`PipelineRunRow`
plus a policy-gated "run manifest" tool. Mutations require
``data:write`` scope on the session.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.persistence.db import get_session
from aqp.persistence.models_pipelines import PipelineManifestRow, PipelineRunRow


class ListPipelineManifestsInput(BaseModel):
    namespace: str | None = None
    enabled_only: bool = False
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ListPipelineManifestsTool(DataMCPTool):
    name = "data.pipelines.list_manifests"
    description = (
        "List registered PipelineManifestRow rows. Useful before "
        "scheduling or running a pipeline."
    )
    args_schema = ListPipelineManifestsInput
    category = "pipelines"
    tags = ("pipelines", "manifests")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        namespace: str | None = None,
        enabled_only: bool = False,
        limit: int = 25,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(PipelineManifestRow)
            if namespace:
                query = query.where(PipelineManifestRow.namespace == namespace)
            if enabled_only:
                query = query.where(PipelineManifestRow.enabled.is_(True))
            rows = (
                session.execute(query.order_by(PipelineManifestRow.name).limit(limit))
                .scalars()
                .all()
            )
            data = [_manifest_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} pipeline manifests",
        )


class GetPipelineRunInput(BaseModel):
    run_id: str = Field(...)


@register_data_mcp_tool
class GetPipelineRunTool(DataMCPTool):
    name = "data.pipelines.get_run"
    description = "Return a PipelineRunRow with its lineage + sink_result + errors."
    args_schema = GetPipelineRunInput
    category = "pipelines"
    tags = ("pipelines", "runs")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        run_id: str,
    ) -> MCPToolResult:
        with get_session() as session:
            row = session.get(PipelineRunRow, run_id)
            if row is None:
                return MCPToolResult(ok=False, error=f"unknown run_id={run_id!r}")
            data = _run_to_dict(row)
        return MCPToolResult(ok=True, data=data, summary=f"pipeline run {run_id}")


class ListPipelineRunsInput(BaseModel):
    manifest_id: str | None = None
    status: str | None = None
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ListPipelineRunsTool(DataMCPTool):
    name = "data.pipelines.list_runs"
    description = "List PipelineRunRow rows, optionally filtered by manifest / status."
    args_schema = ListPipelineRunsInput
    category = "pipelines"
    tags = ("pipelines", "runs")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        manifest_id: str | None = None,
        status: str | None = None,
        limit: int = 25,
    ) -> MCPToolResult:
        with get_session() as session:
            query = select(PipelineRunRow)
            if manifest_id:
                query = query.where(PipelineRunRow.manifest_id == manifest_id)
            if status:
                query = query.where(PipelineRunRow.status == status)
            rows = (
                session.execute(query.order_by(desc(PipelineRunRow.started_at)).limit(limit))
                .scalars()
                .all()
            )
            data = [_run_to_dict(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} pipeline runs",
        )


class RunPipelineManifestInput(BaseModel):
    manifest_id: str = Field(..., description="ID of the PipelineManifestRow to run.")
    overrides: dict[str, Any] | None = None


@register_data_mcp_tool
class RunPipelineManifestTool(DataMCPTool):
    name = "data.pipelines.run_manifest"
    description = (
        "Trigger a pipeline manifest run. Requires data:write scope. "
        "Queues a Celery task via the existing /engine route handlers; "
        "returns the run_id immediately."
    )
    args_schema = RunPipelineManifestInput
    category = "pipelines"
    tags = ("pipelines", "mutating")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=True)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        manifest_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        # Defer to the engine route's existing trigger logic by lazy
        # importing to avoid a circular import at module load.
        try:
            from aqp.tasks.engine_tasks import run_manifest_async  # type: ignore[import-not-found]
        except ImportError:
            return MCPToolResult(
                ok=False, error="engine async task unavailable in this build"
            )
        with get_session() as session:
            manifest = session.get(PipelineManifestRow, manifest_id)
            if manifest is None:
                return MCPToolResult(
                    ok=False, error=f"unknown manifest_id={manifest_id!r}"
                )
        try:
            celery_result = run_manifest_async.delay(
                manifest_id, overrides=overrides or {}
            )
            return MCPToolResult(
                ok=True,
                data={"task_id": str(celery_result.id), "manifest_id": manifest_id},
                summary=f"queued manifest {manifest_id}",
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"queue failed: {exc}")


def _manifest_to_dict(row: PipelineManifestRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "namespace": row.namespace,
        "version": row.version,
        "enabled": bool(row.enabled),
        "owner": row.owner,
        "compute_backend": row.compute_backend,
        "schedule_cron": row.schedule_cron,
        "tags": list(row.tags or []),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_run_status": row.last_run_status,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _run_to_dict(row: PipelineRunRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "manifest_id": row.manifest_id,
        "namespace": row.namespace,
        "name": row.name,
        "backend": row.backend,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_seconds": row.duration_seconds,
        "rows_written": row.rows_written,
        "tables_written": row.tables_written,
        "sink_result": dict(row.sink_result or {}),
        "lineage": dict(row.lineage or {}),
        "errors": list(row.errors or []),
    }


__all__ = [
    "GetPipelineRunTool",
    "ListPipelineManifestsTool",
    "ListPipelineRunsTool",
    "RunPipelineManifestTool",
]
