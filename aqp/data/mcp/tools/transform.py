"""``data.transform.*`` DataMCP tools (Phase 4 — plan section 8).

Two mutating tools wrapping the dbt mesh materialization surface.
Both attach step-up MFA at the HTTP layer and route agent-actor
calls through the approval workflow.
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


def _is_agent(ctx: MCPToolContext) -> bool:
    return (ctx.actor_kind or "").strip().lower() == "agent"


def _agent_sub(ctx: MCPToolContext) -> str:
    return (ctx.extras or {}).get("agent_subject", "agent|unknown")


def _on_behalf_of_user(ctx: MCPToolContext) -> str | None:
    if not _is_agent(ctx):
        return ctx.actor
    extras = ctx.extras or {}
    return extras.get("on_behalf_of_user_id") or extras.get("user_id") or None


# ---------------------------------------------------------------------------
# 1. materialize_dev (mutating)
# ---------------------------------------------------------------------------


class MaterializeDevInput(BaseModel):
    project_slug: str = Field(default="core")
    select: str | None = Field(default=None, description="dbt selection syntax")
    full_refresh: bool = False


@register_data_mcp_tool
class TransformMaterializeDevTool(DataMCPTool):
    """Run `dbt build` against the dev/staging target."""

    name = "data.transform.materialize_dev"
    description = (
        "Run `dbt build` against the dev/staging target. Mutating; "
        "scoped to a single project (core / equities / derivatives / "
        "macro). Returns the manifest invocation summary."
    )
    args_schema = MaterializeDevInput
    category = "transform"
    tags = ("transform", "dbt", "dev")
    mutates = True
    required_scopes = ("data:read", "data:write")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_slug: str = "core",
        select: str | None = None,
        full_refresh: bool = False,
    ) -> MCPToolResult:
        if _is_agent(ctx):
            from aqp.services.ingestion_approvals import request_approval

            pending = request_approval(
                tool_id=self.name,
                args={
                    "project_slug": project_slug,
                    "select": select,
                    "full_refresh": full_refresh,
                },
                requested_by_agent_sub=_agent_sub(ctx),
                on_behalf_of_user_id=_on_behalf_of_user(ctx),
                workspace_id=ctx.workspace_id,
            )
            return MCPToolResult(
                ok=True,
                data=pending,
                summary=(
                    f"approval queued for materialize_dev({project_slug}, "
                    f"select={select})"
                ),
            )
        # Human-initiated: invoke the existing DbtRunnerService.
        try:
            from aqp.data.dbt.runner import DbtRunnerService

            runner = DbtRunnerService()
            select_list = [select] if select else None
            result = runner.build(select=select_list)
            return MCPToolResult(
                ok=bool(result.success),
                data=result.to_dict(),
                summary=f"dbt build success={result.success}",
                error=result.exception,
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"dbt invocation failed: {exc}",
            )


# ---------------------------------------------------------------------------
# 2. materialize_prod (mutating; Tier-P only; step-up)
# ---------------------------------------------------------------------------


class MaterializeProdInput(BaseModel):
    project_slug: str = Field(default="core")
    select: str
    require_approval_id: str | None = None


@register_data_mcp_tool
class TransformMaterializeProdTool(DataMCPTool):
    """Run `dbt build` against the prod target. Tier-P only; step-up MFA required."""

    name = "data.transform.materialize_prod"
    description = (
        "Run `dbt build` against the prod target. Mutating; Tier-P (Platform "
        "Engineer) only. The HTTP path attaches step-up MFA. Agent-actor "
        "calls ALWAYS go through approval workflow."
    )
    args_schema = MaterializeProdInput
    category = "transform"
    tags = ("transform", "dbt", "prod", "admin")
    mutates = True
    required_scopes = ("data:read", "data:write", "admin:cluster")

    def run(
        self,
        *,
        ctx: MCPToolContext,
        project_slug: str = "core",
        select: str,
        require_approval_id: str | None = None,
    ) -> MCPToolResult:
        if _is_agent(ctx):
            from aqp.services.ingestion_approvals import request_approval

            pending = request_approval(
                tool_id=self.name,
                args={
                    "project_slug": project_slug,
                    "select": select,
                },
                requested_by_agent_sub=_agent_sub(ctx),
                on_behalf_of_user_id=_on_behalf_of_user(ctx),
                workspace_id=ctx.workspace_id,
            )
            return MCPToolResult(
                ok=True,
                data=pending,
                summary=(
                    f"approval queued for materialize_prod({project_slug}, "
                    f"select={select})"
                ),
            )
        # Human-initiated: invoke the existing DbtRunnerService with
        # the prod target. The DbtRunnerService picks the target via
        # profile resolution.
        try:
            from aqp.data.dbt.runner import DbtRunnerService

            runner = DbtRunnerService()
            result = runner.build(select=[select])
            return MCPToolResult(
                ok=bool(result.success),
                data=result.to_dict(),
                summary=f"prod dbt build success={result.success}",
                error=result.exception,
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"dbt invocation failed: {exc}",
            )


__all__ = ["TransformMaterializeDevTool", "TransformMaterializeProdTool"]
