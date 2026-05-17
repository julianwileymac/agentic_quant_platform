"""``data.agents.*`` DataMCP tools.

Today: a single read-only ``data.agents.health`` tool that lets the
agentic stack itself (or the GPT-5.5 ``aqp-run-monitor`` subagent)
inspect the AQP-side agent run watchdog without bypassing the
DataMCP boundary (AGENTS rule 22).
"""
from __future__ import annotations

import logging

from pydantic import BaseModel

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


class AgentsHealthInput(BaseModel):
    """No arguments — the snapshot is process-wide."""


@register_data_mcp_tool
class AgentsHealthTool(DataMCPTool):
    name = "data.agents.health"
    description = (
        "Read-only snapshot of the agent stall watchdog — running / "
        "pending / halted counts plus the current stalled-candidate "
        "list. Use this before deciding to call /agents/halt."
    )
    args_schema = AgentsHealthInput
    category = "agents"
    tags = ("agents", "health", "watchdog")
    required_scopes = ("data:read",)

    def run(self, *, ctx: MCPToolContext, **_: object) -> MCPToolResult:
        try:
            from aqp.tasks.agent_watchdog_tasks import collect_health_snapshot
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False,
                error=f"watchdog unavailable: {exc}",
                summary="watchdog unavailable",
            )
        try:
            snap = collect_health_snapshot()
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=str(exc), summary="health failed")
        return MCPToolResult(
            ok=True,
            data=snap,
            rows_returned=len(snap.get("stalled_candidates", [])),
            summary=(
                f"running={snap['running']} pending={snap['pending']} "
                f"halted_24h={snap['halted_last_24h']} stalled={len(snap['stalled_candidates'])}"
            ),
        )


__all__: list[str] = []
