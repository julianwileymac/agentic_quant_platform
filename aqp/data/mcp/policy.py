"""Policy enforcement helpers for DataMCP tools.

Each function raises :class:`aqp.data.mcp.base.MCPPolicyError` when a
constraint is violated; otherwise they return ``None``. Tools either
call them in :meth:`DataMCPTool.policy_check` or rely on the default
:func:`enforce_required_scopes` baked into the base class.
"""
from __future__ import annotations

from typing import Iterable

from aqp.data.mcp.base import MCPPolicyError, MCPToolContext


def enforce_required_scopes(
    ctx: MCPToolContext, required: Iterable[str]
) -> None:
    """Reject calls missing any of the required ``required`` scopes."""
    granted = set(ctx.granted_scopes or ())
    missing = [scope for scope in required if scope not in granted]
    if missing:
        raise MCPPolicyError(
            f"missing required scope(s) {missing!r} (granted: {sorted(granted)})"
        )


def enforce_tenancy(ctx: MCPToolContext, *, required: bool = True) -> None:
    """Reject calls without a tenant context.

    AQP is multi-tenant; agent reads MUST carry ``workspace_id`` and
    (usually) ``project_id`` so :meth:`DataMCPTool.run` can scope its
    Postgres / Iceberg queries. Set ``required=False`` for tools that
    operate on shared reference data (instruments, regulatory corpora,
    macro series).
    """
    if not required:
        return
    if not ctx.workspace_id:
        raise MCPPolicyError("workspace_id is required for this tool")


def enforce_read_only_for_session(
    ctx: MCPToolContext, *, mutates: bool
) -> None:
    """Reject mutating calls unless the session has ``data:write`` scope."""
    if not mutates:
        return
    if "data:write" not in (ctx.granted_scopes or ()):
        raise MCPPolicyError(
            "mutating tools require 'data:write' scope on the session"
        )


def enforce_data_minimization(
    ctx: MCPToolContext, *, requested_columns: list[str], allowed_columns: list[str]
) -> None:
    """Reject calls that request columns outside the allowed sandbox.

    Used by tools that read raw Iceberg tables to ensure agents only
    pull the columns explicitly enumerated in the agent_views (no
    fields containing PII or proprietary risk logic).
    """
    if not requested_columns:
        return
    blocked = [c for c in requested_columns if c not in allowed_columns]
    if blocked:
        raise MCPPolicyError(
            f"columns {blocked!r} are outside the allowed sandbox "
            f"(allowed: {sorted(allowed_columns)})"
        )


__all__ = [
    "enforce_data_minimization",
    "enforce_read_only_for_session",
    "enforce_required_scopes",
    "enforce_tenancy",
]
