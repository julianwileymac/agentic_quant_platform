"""``codebase.find_definition`` / ``codebase.find_references`` tools."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, Field

from aqp.codebase.mcp.base import CodebaseMCPTool, MCPToolContext, MCPToolResult
from aqp.codebase.mcp.index import index_workspace, ripgrep_search
from aqp.codebase.mcp.policy import enforce_path_inside_workspace
from aqp.codebase.mcp.registry import register_codebase_mcp_tool

logger = logging.getLogger(__name__)


class FindInput(BaseModel):
    symbol: str = Field(..., min_length=1)
    root: str | None = None
    max_results: int = Field(default=50, ge=1, le=500)


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
class FindDefinitionTool(CodebaseMCPTool):
    name = "codebase.find_definition"
    description = (
        "Locate every definition of a symbol (class / function / method / "
        "constant) across the workspace. Returns ``[{file, range, kind, language}]``."
    )
    args_schema = FindInput
    category = "search"
    tags = ("codebase", "find_definition")
    required_scopes = ("code:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        symbol: str,
        root: str | None = None,
        max_results: int = 50,
    ) -> MCPToolResult:
        root_path = (
            enforce_path_inside_workspace(ctx, root) if root else _default_root(ctx)
        )
        defs: list[dict] = []
        for sym in index_workspace(root_path):
            if sym.kind in {"module", "import"}:
                continue
            if sym.name != symbol:
                continue
            defs.append(asdict(sym))
            if len(defs) >= max_results:
                break
        return MCPToolResult(
            ok=True,
            data={"definitions": defs},
            rows_returned=len(defs),
            summary=f"{len(defs)} definitions of {symbol!r}",
        )


@register_codebase_mcp_tool
class FindReferencesTool(CodebaseMCPTool):
    name = "codebase.find_references"
    description = (
        "Find every textual reference to a symbol across the workspace. "
        "Uses ripgrep with word boundaries; pair with codebase.find_definition "
        "to separate definitions from call sites."
    )
    args_schema = FindInput
    category = "search"
    tags = ("codebase", "find_references")
    required_scopes = ("code:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        symbol: str,
        root: str | None = None,
        max_results: int = 50,
    ) -> MCPToolResult:
        root_path = (
            enforce_path_inside_workspace(ctx, root) if root else _default_root(ctx)
        )
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
            return MCPToolResult(
                ok=False,
                error=f"symbol {symbol!r} is not a valid identifier",
                summary="bad symbol",
            )
        # ripgrep_search is literal; use word-boundary aware filtering
        # by checking surrounding chars on each hit.
        raw = ripgrep_search(root=root_path, query=symbol, max_results=max_results * 4)
        refs: list[dict] = []
        for m in raw:
            text = m.text
            col = max(0, m.column - 1)
            before = text[col - 1] if col > 0 else " "
            after = text[col + len(symbol)] if col + len(symbol) < len(text) else " "
            if (before.isalnum() or before == "_") or (
                after.isalnum() or after == "_"
            ):
                continue
            refs.append(
                {
                    "file": m.file,
                    "line": m.line,
                    "column": m.column,
                    "text": text,
                }
            )
            if len(refs) >= max_results:
                break
        return MCPToolResult(
            ok=True,
            data={"references": refs},
            rows_returned=len(refs),
            summary=f"{len(refs)} references to {symbol!r}",
        )


__all__: list[str] = []
