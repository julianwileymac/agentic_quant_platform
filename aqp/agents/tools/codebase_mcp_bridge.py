"""Bridge from :class:`aqp.codebase.mcp.CodebaseMCPTool` to ``crewai.tools.BaseTool``.

Mirrors :mod:`aqp.agents.tools.data_mcp_bridge` so the agent runtime
sees the codebase MCP tools through the same single
:data:`aqp.agents.tools.TOOL_REGISTRY` (AGENTS rule 22).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from aqp.auth.contextvars import current_request_context
from aqp.codebase.mcp import (
    CODEBASE_MCP_TOOLS,
    MCPToolContext,
    get_codebase_mcp_tool,
)

logger = logging.getLogger(__name__)


try:  # pragma: no cover
    from crewai.tools import BaseTool as _CrewAIBaseTool  # type: ignore
except ImportError:  # pragma: no cover - dev-only path
    from aqp.agents.tools import BaseTool as _CrewAIBaseTool  # type: ignore[attr-defined]


def _resolve_mcp_context(extra_scopes: tuple[str, ...] = ()) -> MCPToolContext:
    ctx = current_request_context.get()
    workspace_id = getattr(ctx, "workspace_id", None) if ctx is not None else None
    project_id = getattr(ctx, "project_id", None) if ctx is not None else None
    user_id = getattr(ctx, "user_id", None) if ctx is not None else None
    workspace_root: str | None = None
    try:
        from aqp.config import settings

        explicit = str(
            getattr(settings, "codebase_workspace_root", "") or ""
        ).strip()
        workspace_root = explicit or None
    except Exception:  # noqa: BLE001
        workspace_root = None
    granted = ("code:read",) + tuple(extra_scopes)
    return MCPToolContext(
        actor=user_id or "agent_runtime",
        actor_kind="agent",
        workspace_id=workspace_id,
        project_id=project_id,
        workspace_root=workspace_root,
        granted_scopes=granted,
    )


def make_bridge_tool_class(mcp_tool_name: str) -> type:
    if mcp_tool_name not in CODEBASE_MCP_TOOLS:
        raise KeyError(f"unknown CodebaseMCPTool {mcp_tool_name!r}")
    cls = CODEBASE_MCP_TOOLS[mcp_tool_name]
    _tool_name = cls.name
    _tool_desc = (cls.description or "").strip()
    _tool_schema = cls.args_schema
    bridge_class_name = f"CodebaseMCP_{cls.__name__}_Bridge"

    # Note: we use ``_tool_*`` locals (not ``name`` / ``description`` /
    # ``args_schema``) so the class body doesn't trigger the Python
    # ≥3.13 ``NameError`` where the annotation RHS cannot see the
    # enclosing function's variable when the names match.
    class _BridgeTool(_CrewAIBaseTool):  # type: ignore[misc, valid-type]
        name: str = _tool_name
        description: str = _tool_desc
        args_schema: type[BaseModel] | None = _tool_schema

        def _run(self, **kwargs: Any) -> str:  # type: ignore[override]
            tool = get_codebase_mcp_tool(mcp_tool_name)
            ctx = _resolve_mcp_context()
            result = tool.invoke(ctx=ctx, **kwargs)
            try:
                return json.dumps(result.to_json(), default=str)
            except Exception:  # noqa: BLE001
                return json.dumps(
                    {"ok": False, "error": "result serialization failed"}
                )

    _BridgeTool.__name__ = bridge_class_name
    _BridgeTool.__qualname__ = bridge_class_name
    return _BridgeTool


def install_codebase_mcp_tools(target_registry: dict[str, type]) -> list[str]:
    """Wrap every :class:`CodebaseMCPTool` and merge into ``target_registry``."""
    installed: list[str] = []
    for name in sorted(CODEBASE_MCP_TOOLS):
        try:
            wrapper = make_bridge_tool_class(name)
        except Exception:  # noqa: BLE001
            logger.exception("failed to bridge CodebaseMCPTool %s", name)
            continue
        target_registry[name] = wrapper
        installed.append(name)
    return installed


__all__ = ["install_codebase_mcp_tools", "make_bridge_tool_class", "_resolve_mcp_context"]
