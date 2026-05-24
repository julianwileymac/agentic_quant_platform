"""DataMCP agent ↔ rate-limit bridge.

Translates :class:`aqp.data.mcp.base.MCPToolContext` into the ``ctx``
shape :class:`PerAgentStrategy` expects so the dual-debit happens
automatically whenever a tool is invoked from a delegated agent
token (root AGENTS.md rule 54).
"""
from __future__ import annotations

from typing import Any


def build_ratelimit_ctx(mcp_ctx: Any | None) -> dict[str, Any]:
    """Build the ``ctx`` dict the strategies consume.

    Reads :class:`MCPToolContext.actor_kind` and the
    ``agent_subject`` extracted from the delegated JWT's ``act.sub``
    claim. Returns an empty dict for user-initiated calls so the
    inner strategy (per-user) decides alone.
    """
    if mcp_ctx is None:
        return {}
    actor_kind = getattr(mcp_ctx, "actor_kind", None)
    if not actor_kind:
        return {}
    out: dict[str, Any] = {"actor_kind": str(actor_kind)}
    extras = getattr(mcp_ctx, "extras", None) or {}
    if isinstance(extras, dict):
        if "agent_subject" in extras:
            out["agent_subject"] = str(extras["agent_subject"])
        if "agent_policy" in extras:
            out["agent_policy"] = dict(extras["agent_policy"])
        if "request_hash" in extras:
            out["request_hash"] = extras["request_hash"]
    return out


__all__ = ["build_ratelimit_ctx"]
