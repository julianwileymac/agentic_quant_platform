"""``codebase.search`` — hybrid lexical + AST-kind filtered search."""
from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from aqp.codebase.mcp.base import CodebaseMCPTool, MCPToolContext, MCPToolResult
from aqp.codebase.mcp.index import index_workspace, ripgrep_search
from aqp.codebase.mcp.policy import enforce_path_inside_workspace
from aqp.codebase.mcp.registry import register_codebase_mcp_tool

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    query: str = Field(..., min_length=1, description="Literal string to search for.")
    root: str | None = Field(
        default=None,
        description="Optional workspace-relative root override; must stay inside the workspace.",
    )
    language: Literal["python", "typescript", "sql", "markdown", "yaml"] | None = None
    kind: Literal[
        "class", "function", "method", "constant", "import", "section", "module"
    ] | None = None
    k: int = Field(default=20, ge=1, le=200)
    mode: Literal["hybrid", "lexical", "ast"] = Field(default="hybrid")


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
class CodebaseSearchTool(CodebaseMCPTool):
    name = "codebase.search"
    description = (
        "Hybrid search across the AQP workspace: ripgrep-style lexical search "
        "combined with AST-kind filtering (class / function / method / constant / "
        "import / section / module). Use this before reading whole files — it "
        "returns up to ``k`` localised snippets the agent can read directly."
    )
    args_schema = SearchInput
    category = "search"
    tags = ("codebase", "search", "hybrid")
    required_scopes = ("code:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        query: str,
        root: str | None = None,
        language: str | None = None,
        kind: str | None = None,
        k: int = 20,
        mode: str = "hybrid",
    ) -> MCPToolResult:
        root_path = (
            enforce_path_inside_workspace(ctx, root) if root else _default_root(ctx)
        )
        results: list[dict] = []
        if mode in {"hybrid", "lexical"}:
            for match in ripgrep_search(root=root_path, query=query, max_results=k):
                results.append(
                    {
                        "file": match.file,
                        "line": match.line,
                        "column": match.column,
                        "text": match.text,
                        "score": match.score,
                        "source": "lexical",
                    }
                )
                if len(results) >= k:
                    break
        if mode in {"hybrid", "ast"} and len(results) < k:
            for sym in index_workspace(root_path):
                if kind and sym.kind != kind:
                    continue
                if language and sym.language != language:
                    continue
                if query.lower() not in sym.name.lower():
                    continue
                results.append(
                    {
                        "file": sym.file,
                        "line": sym.start_line,
                        "column": 1,
                        "text": f"{sym.kind} {sym.name}",
                        "score": 0.5,
                        "source": "ast",
                        "symbol_name": sym.name,
                        "symbol_kind": sym.kind,
                    }
                )
                if len(results) >= k:
                    break
        return MCPToolResult(
            ok=True,
            data={"matches": results[:k]},
            rows_returned=len(results[:k]),
            summary=f"{len(results[:k])} hits for {query!r}",
        )


__all__: list[str] = []
