"""External MCP server for the AQP codebase layer.

Exposes :data:`aqp.codebase.mcp.CODEBASE_MCP_TOOLS` over two transports:

- Streamable HTTP (FastAPI router at ``/mcp/codebase``)
- stdio (the ``aqp-codebase-mcp`` console script)

Mirrors :mod:`aqp.data.mcp.server` so Cursor / Claude Desktop can use
the same connection pattern they already use for ``aqp-data-mcp``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from aqp.api.mcp_audience import (
    get_codebase_mcp_canonical_uri,
    get_mcp_audience_mode,
    validate_mcp_audience,
)
from aqp.codebase.mcp import (
    CODEBASE_MCP_TOOLS,
    MCPToolContext,
    get_codebase_mcp_tool,
    list_codebase_mcp_tools,
)

logger = logging.getLogger(__name__)


class MCPInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = None
    actor_kind: str | None = None
    session_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    workspace_root: str | None = None
    granted_scopes: list[str] = Field(default_factory=lambda: ["code:read"])
    request_id: str | None = None


# ---------------------------------------------------------------------------
# FastAPI streamable HTTP transport
# ---------------------------------------------------------------------------


def build_codebase_mcp_router() -> APIRouter:
    """Return a FastAPI router exposing the codebase MCP tool catalog."""
    router = APIRouter(prefix="/mcp/codebase", tags=["codebase-mcp"])

    @router.get("/tools")
    def list_tools() -> dict[str, Any]:
        return {
            "ok": True,
            "tools": list_codebase_mcp_tools(),
            "count": len(CODEBASE_MCP_TOOLS),
        }

    @router.get("/tools/{name}")
    def describe_tool(name: str) -> dict[str, Any]:
        if name not in CODEBASE_MCP_TOOLS:
            raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
        return {
            "ok": True,
            "tool": CODEBASE_MCP_TOOLS[name].to_mcp_tool_descriptor(),
        }

    @router.post("/tools/{name}/invoke")
    def invoke_tool(name: str, body: MCPInvokeRequest, request: Request) -> dict[str, Any]:
        # Auth is enforced by the FastAPI dependency stack at the
        # main app level (mirroring /mcp/data). External callers must
        # carry the AQP_M2M_TOKEN; local dev with auth_provider=local
        # is allowed through unauthenticated.
        if name not in CODEBASE_MCP_TOOLS:
            raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
        # RFC 8707 audience binding (workstream E). Mirrors the data
        # MCP server. The validator no-ops when
        # ``AQP_MCP_REQUIRE_RFC8707=off`` (default) and only enforces
        # once the operator flips the knob after permissive soak.
        validate_mcp_audience(
            request,
            get_codebase_mcp_canonical_uri(),
            mode=get_mcp_audience_mode(),
        )
        ctx = MCPToolContext(
            actor=body.actor or "codebase_mcp_http",
            actor_kind=body.actor_kind or "service",
            session_id=body.session_id,
            workspace_id=body.workspace_id,
            project_id=body.project_id,
            workspace_root=body.workspace_root,
            granted_scopes=tuple(body.granted_scopes or ("code:read",)),
            request_id=body.request_id,
        )
        tool = get_codebase_mcp_tool(name)
        result = tool.invoke(ctx=ctx, **(body.arguments or {}))
        return {"ok": result.ok, "result": result.to_json()}

    return router


# ---------------------------------------------------------------------------
# stdio transport
# ---------------------------------------------------------------------------


def _validate_stdio_token() -> dict[str, Any] | None:
    import os

    try:
        from aqp.config import settings
    except Exception:  # noqa: BLE001
        return {}

    if str(getattr(settings, "auth_provider", "local")).lower() == "local":
        return {}

    token = os.environ.get("AQP_M2M_TOKEN") or ""
    if not token:
        return None
    try:
        from aqp.auth.oidc import get_oidc_config, validate_jwt

        cfg = get_oidc_config()
        if cfg is None:
            return None
        return validate_jwt(token, config=cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AQP_M2M_TOKEN validation failed: %s", exc)
        return None


_STDIO_AUTH_CLAIMS: dict[str, Any] | None = None


def _stdio_actor() -> str:
    if isinstance(_STDIO_AUTH_CLAIMS, dict):
        sub = _STDIO_AUTH_CLAIMS.get("sub")
        if isinstance(sub, str) and sub:
            return sub
    return "external_stdio"


async def _handle_stdio_line(line: str) -> dict[str, Any]:
    line = line.strip()
    if not line:
        return {"ok": False, "error": "empty line"}
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid json: {exc}"}
    method = payload.get("method")
    params = payload.get("params") or {}
    request_id = payload.get("id")
    response: dict[str, Any]

    if method == "tools/list":
        response = {
            "ok": True,
            "id": request_id,
            "result": {
                "tools": list_codebase_mcp_tools(),
                "count": len(CODEBASE_MCP_TOOLS),
            },
        }
    elif method == "tools/describe":
        name = params.get("name")
        if name not in CODEBASE_MCP_TOOLS:
            response = {"ok": False, "id": request_id, "error": f"unknown tool {name!r}"}
        else:
            response = {
                "ok": True,
                "id": request_id,
                "result": CODEBASE_MCP_TOOLS[name].to_mcp_tool_descriptor(),
            }
    elif method == "tools/invoke":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        actor = _stdio_actor()
        ctx = MCPToolContext(
            actor=actor,
            actor_kind=params.get("actor_kind") or "service",
            session_id=params.get("session_id"),
            workspace_id=params.get("workspace_id"),
            project_id=params.get("project_id"),
            workspace_root=params.get("workspace_root"),
            granted_scopes=tuple(params.get("granted_scopes") or ("code:read",)),
            request_id=params.get("request_id"),
        )
        if name not in CODEBASE_MCP_TOOLS:
            response = {"ok": False, "id": request_id, "error": f"unknown tool {name!r}"}
        else:
            tool = get_codebase_mcp_tool(name)
            result = tool.invoke(ctx=ctx, **arguments)
            response = {
                "ok": result.ok,
                "id": request_id,
                "result": result.to_json(),
            }
    elif method == "ping":
        response = {
            "ok": True,
            "id": request_id,
            "result": {"server": "aqp-codebase-mcp", "ts": datetime.utcnow().isoformat()},
        }
    else:
        response = {"ok": False, "id": request_id, "error": f"unknown method {method!r}"}
    return response


async def _stdio_loop() -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            break
        text = line_bytes.decode("utf-8", errors="replace")
        response = await _handle_stdio_line(text)
        try:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001
            logger.exception("stdio response write failed")


def run_stdio() -> int:
    """Console-script entry point for ``aqp-codebase-mcp``."""
    global _STDIO_AUTH_CLAIMS
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    _STDIO_AUTH_CLAIMS = _validate_stdio_token()
    if _STDIO_AUTH_CLAIMS is None:
        sys.stderr.write(
            "aqp-codebase-mcp: AQP_M2M_TOKEN required when auth_provider != 'local'\n"
        )
        return 2
    logger.info(
        "aqp-codebase-mcp stdio server starting; %d tools registered (actor=%s)",
        len(CODEBASE_MCP_TOOLS),
        _stdio_actor(),
    )
    try:
        asyncio.run(_stdio_loop())
    except KeyboardInterrupt:
        logger.info("aqp-codebase-mcp stopped")
    return 0


__all__ = ["build_codebase_mcp_router", "run_stdio"]
