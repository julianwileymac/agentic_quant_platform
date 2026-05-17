"""AQP Codebase MCP — agent-readable view of the AQP repository.

This package mirrors the layout of :mod:`aqp.data.mcp`: a uniform
:class:`CodebaseMCPTool` ABC, a registry decorator, a policy layer,
and two transports (FastAPI streamable HTTP + stdio for Cursor /
Claude Desktop).

Why a sibling package instead of more :class:`DataMCPTool` subclasses?

- The codebase view is **read-mostly** and orthogonal to AQP's data
  plane. Splitting the registries keeps the data MCP tool list
  uncluttered and lets us use different scope strings
  (``code:read`` / ``code:write``) without polluting the
  ``data:*`` family.
- The codebase tools need a workspace-path allow-list (the
  :mod:`aqp.codebase.mcp.policy` module) that is not relevant to
  data tools.
- The same bridge pattern installs them into
  :data:`aqp.agents.tools.TOOL_REGISTRY` via
  :mod:`aqp.agents.tools.codebase_mcp_bridge` so AgentRuntime
  sees both registries through one tool catalog (AGENTS rule 22).

Hard rules this package honours:

- **Rule 2** — every LLM call goes through ``router_complete``.
  ``codebase.elaborate_finding`` is the only tool that touches an
  LLM and it lives in :mod:`aqp.codebase.mcp.tools.elaborate`.
- **Rule 11** — every embedding write goes through
  :class:`aqp.rag.HierarchicalRAG` into the new ``code_chunks``
  corpus. The index module never touches Redis / pgvector directly.
- **Rule 22** — ``CodebaseMCPTool`` is the only way agents reach
  source code. No ORM imports inside ``aqp/codebase/`` or
  ``aqp/agents/``.
- **Rule 26** — external endpoints (SERA, …) resolve credentials
  through :class:`aqp.credentials.CredentialResolver`.
"""
from __future__ import annotations

from aqp.codebase.mcp import (
    CODEBASE_MCP_TOOLS,
    CodebaseMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
    get_codebase_mcp_tool,
    list_codebase_mcp_tools,
    register_codebase_mcp_tool,
)

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
