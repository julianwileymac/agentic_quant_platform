"""``data.oauth.list_connections`` MCP tool (Workstream D).

Read-only DataMCP tool that lets an agent inspect the active set of
external OAuth connections for the calling user. Pairs with the new
:class:`UserOAuthTokenStore` so the agent can decide whether the
user has authorised AQP to call a given source before attempting it.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool


class ListOAuthConnectionsInput(BaseModel):
    include_revoked: bool = Field(default=False)
    limit: int = Field(default=20, ge=1, le=200)


@register_data_mcp_tool
class ListOAuthConnectionsTool(DataMCPTool):
    """Read-only view of the calling user's external OAuth connections."""

    name = "data.oauth.list_connections"
    description = (
        "List the active external OAuth2 connections (Bloomberg, GitHub, "
        "Refinitiv, FRED, ...) the calling user has authorised. Returns "
        "connection metadata only — never the access token itself."
    )
    args_schema = ListOAuthConnectionsInput
    category = "identity"
    tags = ("oauth", "credentials")
    required_scopes = ("data:read",)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        include_revoked: bool = False,
        limit: int = 20,
    ) -> MCPToolResult:
        from aqp.persistence.db import get_session
        from aqp.persistence.models_oauth_tokens import UserOAuthToken

        user_id = ctx.actor if ctx.actor_kind == "user" else None
        if not user_id:
            return MCPToolResult(
                ok=True,
                data={"connections": []},
                summary="no user context",
            )
        with get_session() as session:
            query = session.query(UserOAuthToken).filter(
                UserOAuthToken.user_id == user_id
            )
            if not include_revoked:
                query = query.filter(UserOAuthToken.revoked_at.is_(None))
            rows = (
                query.order_by(UserOAuthToken.created_at.desc()).limit(int(limit)).all()
            )
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "id": str(row.id),
                    "source": row.source,
                    "scopes": list(row.scopes or []),
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "label": row.label,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
                }
            )
        return MCPToolResult(
            ok=True,
            data={"connections": out},
            summary=f"{len(out)} external oauth connections",
        )


__all__ = ["ListOAuthConnectionsTool"]
