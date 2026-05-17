"""Data Model Context Protocol (DataMCP) tool catalog.

A single source of truth for every "data tool" exposed to LLM agents,
both:

- in-process via :class:`aqp.agents.tools.TOOL_REGISTRY` (bridge in
  :mod:`aqp.agents.tools.data_mcp_bridge`)
- externally via the FastAPI MCP server in :mod:`aqp.data.mcp.server`
  (stdio + streamable HTTP)

Each :class:`DataMCPTool` declares strictly typed input parameters
(Pydantic ``args_schema``), a semantic description for the LLM
router, a ``policy_check`` for tenancy / rate / scope, and an
``actor`` indicator so the lineage observer can attribute the call.

This package implements the architectural blueprint's MCP boundary:
agents read catalog / entities / pipelines / sinks / streaming data
exclusively through these tools. Direct PG / Iceberg reads from
agent code are forbidden by ``.cursor/rules/aqp.mdc``.
"""
from __future__ import annotations

from aqp.data.mcp.base import (
    DataMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
)
from aqp.data.mcp.policy import (
    enforce_data_minimization,
    enforce_read_only_for_session,
    enforce_tenancy,
)
from aqp.data.mcp.registry import (
    DATA_MCP_TOOLS,
    get_data_mcp_tool,
    list_data_mcp_tools,
    register_data_mcp_tool,
)

# Side-effect imports so the registry is fully populated when this
# package is loaded.
from aqp.data.mcp.tools import (  # noqa: F401  (registers tools)
    arbitrage,
    catalog,
    datahub,
    entities,
    futures,
    iceberg,
    identity,
    instruments,
    optimal_control,
    pipelines,
    pricing,
    sinks,
    sources,
    strategy_config,
    streaming,
)

__all__ = [
    "DATA_MCP_TOOLS",
    "DataMCPTool",
    "MCPPolicyError",
    "MCPToolContext",
    "MCPToolResult",
    "enforce_data_minimization",
    "enforce_read_only_for_session",
    "enforce_tenancy",
    "get_data_mcp_tool",
    "list_data_mcp_tools",
    "register_data_mcp_tool",
]
