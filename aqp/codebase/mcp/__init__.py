"""Codebase MCP package — base classes, registry, policy, server."""
from __future__ import annotations

from aqp.codebase.mcp.base import (
    CodebaseMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
)
from aqp.codebase.mcp.registry import (
    CODEBASE_MCP_TOOLS,
    get_codebase_mcp_tool,
    list_codebase_mcp_tools,
    register_codebase_mcp_tool,
)

# Import tools for their @register_codebase_mcp_tool side effects.
from aqp.codebase.mcp import tools  # noqa: F401 - side-effect import

__all__ = [
    "CODEBASE_MCP_TOOLS",
    "CodebaseMCPTool",
    "MCPPolicyError",
    "MCPToolContext",
    "MCPToolResult",
    "get_codebase_mcp_tool",
    "list_codebase_mcp_tools",
    "register_codebase_mcp_tool",
]
