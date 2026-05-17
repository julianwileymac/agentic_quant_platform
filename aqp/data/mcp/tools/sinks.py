"""Sink registry DataMCP tools."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_read_only_for_session, enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool
from aqp.data.sinks.service import (
    list_sinks as service_list_sinks,
    materialise_node_spec as service_materialise_node_spec,
    sink_summary,
)
from aqp.persistence.db import get_session


class ListSinksInput(BaseModel):
    kind: str | None = None
    enabled_only: bool = False
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ListSinksTool(DataMCPTool):
    name = "data.sinks.list"
    description = "List registered sinks for the current project."
    args_schema = ListSinksInput
    category = "sinks"
    tags = ("sinks", "list")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        kind: str | None = None,
        enabled_only: bool = False,
        limit: int = 25,
    ) -> MCPToolResult:
        with get_session() as session:
            rows = service_list_sinks(
                session,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                kind=kind,
                enabled_only=enabled_only,
                limit=limit,
            )
            data = [sink_summary(row) for row in rows]
        return MCPToolResult(
            ok=True,
            data=data,
            rows_returned=len(data),
            summary=f"listed {len(data)} sinks",
        )


class MaterialiseSinkInput(BaseModel):
    sink_id: str = Field(...)
    overrides: dict[str, Any] | None = None


@register_data_mcp_tool
class MaterialiseSinkTool(DataMCPTool):
    name = "data.sinks.materialise"
    description = (
        "Resolve a SinkRow into a concrete NodeSpec for a manifest. "
        "Read-only with respect to the sink registry but emits a 'sink' "
        "lineage event so callers can audit who materialised which sink."
    )
    args_schema = MaterialiseSinkInput
    category = "sinks"
    tags = ("sinks", "materialise")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        sink_id: str,
        overrides: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        with get_session() as session:
            spec = service_materialise_node_spec(
                session, sink_id, overrides=overrides or None
            )
        return MCPToolResult(
            ok=True,
            data={
                "name": spec.name,
                "kwargs": dict(spec.kwargs or {}),
                "label": spec.label,
                "enabled": bool(spec.enabled),
            },
            summary=f"materialised sink {sink_id} -> {spec.name}",
        )


__all__ = ["ListSinksTool", "MaterialiseSinkTool"]
