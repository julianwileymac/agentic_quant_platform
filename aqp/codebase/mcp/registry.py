"""Registry of every :class:`CodebaseMCPTool` (mirrors data MCP registry)."""
from __future__ import annotations

import logging
from typing import Any

from aqp.codebase.mcp.base import CodebaseMCPTool

logger = logging.getLogger(__name__)


CODEBASE_MCP_TOOLS: dict[str, type[CodebaseMCPTool]] = {}


def register_codebase_mcp_tool(cls: type[CodebaseMCPTool]) -> type[CodebaseMCPTool]:
    """Decorator that registers a :class:`CodebaseMCPTool` subclass."""
    if not issubclass(cls, CodebaseMCPTool):
        raise TypeError(f"{cls!r} must subclass CodebaseMCPTool")
    name = (cls.name or "").strip()
    if not name:
        raise ValueError(f"{cls.__name__} must set ``name``")
    if name in CODEBASE_MCP_TOOLS and CODEBASE_MCP_TOOLS[name] is not cls:
        logger.debug("Replacing CodebaseMCPTool registration for %s", name)
    CODEBASE_MCP_TOOLS[name] = cls
    return cls


def get_codebase_mcp_tool(name: str) -> CodebaseMCPTool:
    if name not in CODEBASE_MCP_TOOLS:
        raise KeyError(
            f"unknown CodebaseMCPTool {name!r}; registered: {sorted(CODEBASE_MCP_TOOLS)}"
        )
    return CODEBASE_MCP_TOOLS[name]()


def list_codebase_mcp_tools() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in sorted(CODEBASE_MCP_TOOLS):
        cls = CODEBASE_MCP_TOOLS[name]
        out.append(cls.to_mcp_tool_descriptor())
    return out


__all__ = [
    "CODEBASE_MCP_TOOLS",
    "get_codebase_mcp_tool",
    "list_codebase_mcp_tools",
    "register_codebase_mcp_tool",
]
