"""``codebase.get_repo_graph`` — adjacency slice of the codebase graph."""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from aqp.codebase.mcp.base import CodebaseMCPTool, MCPToolContext, MCPToolResult
from aqp.codebase.mcp.index import build_graph_from_symbols, index_workspace
from aqp.codebase.mcp.policy import enforce_path_inside_workspace
from aqp.codebase.mcp.registry import register_codebase_mcp_tool

logger = logging.getLogger(__name__)


class RepoGraphInput(BaseModel):
    root: str | None = Field(
        default=None, description="Workspace-relative root for the graph build."
    )
    file: str | None = Field(
        default=None,
        description="If set, return only the subgraph rooted at this file.",
    )
    depth: int = Field(default=1, ge=0, le=5)


def _default_root(ctx: MCPToolContext) -> Path:
    if ctx.workspace_root:
        return Path(ctx.workspace_root).resolve()
    try:
        from aqp.config import settings

        explicit = str(getattr(settings, "codebase_workspace_root", "") or "").strip()
        if explicit:
            return Path(explicit).resolve()
    except Exception:  # noqa: BLE001
        pass
    return Path.cwd().resolve()


@register_codebase_mcp_tool
class GetRepoGraphTool(CodebaseMCPTool):
    name = "codebase.get_repo_graph"
    description = (
        "Return an adjacency slice of the AQP codebase graph. Without "
        "``file`` you get the entire graph (use carefully on large "
        "workspaces); with ``file`` and ``depth`` you get a bounded "
        "BFS slice — agents use this to ask \"what depends on this module?\"."
    )
    args_schema = RepoGraphInput
    category = "graph"
    tags = ("codebase", "graph", "dependency")
    required_scopes = ("code:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        root: str | None = None,
        file: str | None = None,
        depth: int = 1,
    ) -> MCPToolResult:
        root_path = (
            enforce_path_inside_workspace(ctx, root) if root else _default_root(ctx)
        )
        target = None
        if file:
            target_path = enforce_path_inside_workspace(ctx, file)
            target = str(target_path)
        symbols = index_workspace(root_path)
        g = build_graph_from_symbols(symbols)
        slice_dict = g.slice(file=target, depth=depth)
        return MCPToolResult(
            ok=True,
            data={"graph": slice_dict, "node_count": len(slice_dict)},
            rows_returned=len(slice_dict),
            summary=f"graph slice rooted at {target or '<all>'} (depth={depth}, nodes={len(slice_dict)})",
        )


__all__: list[str] = []
