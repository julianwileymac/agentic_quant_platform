"""FastAPI router + stdio runner for the dedicated MLOps MCP server.

The server reuses :data:`aqp.data.mcp.DATA_MCP_TOOLS` but filters to
the ``data.ml.*`` slice so clients minting tokens for the MLOps
audience cannot reach unrelated data-layer tools. Per Hard Rule 49,
every ``tools/call`` validates the JWT's audience against
``settings.mcp_ml_canonical_uri`` and returns the RFC 9728
``WWW-Authenticate`` header on rejection.

Outbound calls always mint their own M2M tokens via
:class:`aqp.auth.m2m.M2MTokenIssuer` — never forward the user's bearer
(``test_no_token_passthrough`` linter enforces this at CI time).
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
    get_mcp_audience_mode,
    validate_mcp_audience,
)
from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    require_authenticated,
)
from aqp.data.mcp import DATA_MCP_TOOLS, MCPToolContext
from aqp.data.mcp.base import DataMCPTool

logger = logging.getLogger(__name__)


_MCP_ML_PREFIX = "data.ml."


def _ml_tool_names() -> list[str]:
    return sorted(name for name in DATA_MCP_TOOLS if name.startswith(_MCP_ML_PREFIX))


def _ml_tool_cls(name: str) -> type[DataMCPTool] | None:
    if not name.startswith(_MCP_ML_PREFIX):
        return None
    return DATA_MCP_TOOLS.get(name)


def get_ml_mcp_canonical_uri() -> str:
    """Return ``settings.mcp_ml_canonical_uri`` defensively (Hard Rule 49)."""
    try:
        from aqp.config import settings

        return str(getattr(settings, "mcp_ml_canonical_uri", "") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# FastAPI streamable HTTP transport
# ---------------------------------------------------------------------------


class MLInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = None
    actor_kind: str | None = None
    session_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    granted_scopes: list[str] = Field(default_factory=lambda: ["data:read"])
    request_id: str | None = None


def build_ml_mcp_router() -> APIRouter:
    """FastAPI router for the MLOps MCP HTTP transport."""
    router = APIRouter(prefix="/mcp/ml", tags=["ml-mcp"])

    @router.get("/tools")
    def list_tools() -> dict[str, Any]:
        names = _ml_tool_names()
        tools = [DATA_MCP_TOOLS[name].to_mcp_tool_descriptor() for name in names]
        return {"ok": True, "tools": tools, "count": len(tools)}

    @router.get("/tools/{name}")
    def describe_tool(name: str) -> dict[str, Any]:
        cls = _ml_tool_cls(name)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"unknown ml tool {name!r}")
        return {"ok": True, "tool": cls.to_mcp_tool_descriptor()}

    @router.post("/tools/{name}/invoke")
    def invoke_tool(
        name: str,
        body: MLInvokeRequest,
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> dict[str, Any]:
        cls = _ml_tool_cls(name)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"unknown ml tool {name!r}")
        # RFC 8707 audience binding against the MLOps canonical URI
        # (Hard Rule 49). When mode == 'off' the helper no-ops; when
        # 'strict' the call raises HTTPException(401) with the WWW-
        # Authenticate header pointing at /.well-known/.../mcp/ml.
        validate_mcp_audience(
            request,
            get_ml_mcp_canonical_uri(),
            mode=get_mcp_audience_mode(),
        )
        claims = getattr(request.state, "oidc_claims", None) or {}
        act = claims.get("act") if isinstance(claims, dict) else None
        on_behalf_of: str | None = None
        agent_subject: str | None = None
        if isinstance(act, dict):
            agent_subject = str(act.get("sub") or "") or None
            on_behalf_of = str(claims.get("sub") or "") or None
        mcp_ctx = MCPToolContext(
            actor=agent_subject or user.id,
            actor_kind="agent" if agent_subject else (body.actor_kind or "user"),
            session_id=body.session_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            granted_scopes=tuple(body.granted_scopes or ("data:read",)),
            request_id=body.request_id,
        )
        tool = cls()
        result = tool.invoke(ctx=mcp_ctx, **(body.arguments or {}))
        payload = {"ok": result.ok, "result": result.to_json()}
        if on_behalf_of:
            payload["actor"] = {
                "agent_sub": agent_subject,
                "on_behalf_of_sub": on_behalf_of,
            }
        return payload

    return router


# ---------------------------------------------------------------------------
# stdio transport — ``aqp-ml-mcp`` console script
# ---------------------------------------------------------------------------


def _validate_stdio_token() -> dict[str, Any] | None:
    import os

    try:
        from aqp.config import settings
    except Exception:
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
        logger.warning("aqp-ml-mcp: AQP_M2M_TOKEN validation failed: %s", exc)
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

    if method == "tools/list":
        names = _ml_tool_names()
        tools = [DATA_MCP_TOOLS[name].to_mcp_tool_descriptor() for name in names]
        return {
            "ok": True,
            "id": request_id,
            "result": {"tools": tools, "count": len(tools)},
        }

    if method == "tools/describe":
        name = str(params.get("name") or "")
        cls = _ml_tool_cls(name)
        if cls is None:
            return {"ok": False, "id": request_id, "error": f"unknown ml tool {name!r}"}
        return {"ok": True, "id": request_id, "result": cls.to_mcp_tool_descriptor()}

    if method == "tools/invoke":
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        cls = _ml_tool_cls(name)
        if cls is None:
            return {"ok": False, "id": request_id, "error": f"unknown ml tool {name!r}"}
        ctx = MCPToolContext(
            actor=_stdio_actor(),
            actor_kind=params.get("actor_kind") or "service",
            session_id=params.get("session_id"),
            workspace_id=params.get("workspace_id"),
            project_id=params.get("project_id"),
            granted_scopes=tuple(params.get("granted_scopes") or ("data:read",)),
            request_id=params.get("request_id"),
        )
        tool = cls()
        result = tool.invoke(ctx=ctx, **arguments)
        return {
            "ok": result.ok,
            "id": request_id,
            "result": result.to_json(),
        }

    if method == "ping":
        return {
            "ok": True,
            "id": request_id,
            "result": {"server": "aqp-ml-mcp", "ts": datetime.utcnow().isoformat()},
        }

    return {"ok": False, "id": request_id, "error": f"unknown method {method!r}"}


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
    """Console-script entry for ``aqp-ml-mcp``.

    Requires ``$AQP_M2M_TOKEN`` in OIDC mode (Hard Rule 49 / 27).
    """
    global _STDIO_AUTH_CLAIMS
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    _STDIO_AUTH_CLAIMS = _validate_stdio_token()
    if _STDIO_AUTH_CLAIMS is None:
        sys.stderr.write(
            "aqp-ml-mcp: AQP_M2M_TOKEN is required when auth_provider != 'local'\n"
        )
        return 2
    tools = _ml_tool_names()
    logger.info(
        "aqp-ml-mcp stdio server starting; %d tools registered (actor=%s)",
        len(tools),
        _stdio_actor(),
    )
    try:
        asyncio.run(_stdio_loop())
    except KeyboardInterrupt:
        logger.info("aqp-ml-mcp stopped")
    return 0


__all__ = ["build_ml_mcp_router", "get_ml_mcp_canonical_uri", "run_stdio"]
