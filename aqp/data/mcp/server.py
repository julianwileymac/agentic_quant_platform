"""External MCP server for the AQP data layer.

Exposes :data:`aqp.data.mcp.DATA_MCP_TOOLS` over two transports:

- **Streamable HTTP** (FastAPI router mountable at ``/mcp/data``)
- **stdio** (a thin runner used by the ``aqp-data-mcp`` console
  script for Cursor / Claude Desktop integrations)

Both transports go through the same per-call policy checks
(:meth:`DataMCPTool.policy_check`) and emit lineage events through
the writer-observer in :mod:`aqp.data.catalog.lineage`.

The "real" MCP wire protocol is provided by the optional ``mcp``
Python SDK; when it isn't installed the FastAPI router still works
(returns the same JSON shape) but the stdio runner falls back to a
minimal line-based JSON protocol so smoke tests can still exercise
the surface.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from fastapi import Request

from aqp.api.mcp_audience import (
    get_data_mcp_canonical_uri,
    get_mcp_audience_mode,
    validate_mcp_audience,
)
from aqp.auth import (
    CurrentUser,
    RequestContext,
    current_context,
    require_authenticated,
)
from aqp.data.mcp import (
    DATA_MCP_TOOLS,
    MCPToolContext,
)
from aqp.data.mcp.base import DataMCPTool, MCPToolResult
from aqp.data.mcp.event_bus import FeedEvent, get_feed_event_bus

logger = logging.getLogger(__name__)


_DYNAMIC_FEED_TOOL_PREFIX = "data.feeds."
_DYNAMIC_FEED_TOOL_NAMES: set[str] = set()
_DYNAMIC_FEED_LOCK = threading.RLock()
_DYNAMIC_FEED_UNSUBSCRIBE: Callable[[], None] | None = None


# ---------------------------------------------------------------------------
# FastAPI streamable HTTP transport
# ---------------------------------------------------------------------------


class MCPInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    actor: str | None = None
    actor_kind: str | None = None
    session_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    granted_scopes: list[str] = Field(default_factory=lambda: ["data:read"])
    request_id: str | None = None


class _FeedSyncToolArgs(BaseModel):
    """Shared args schema for dynamic per-feed sync tools."""

    time_window: tuple[str, str] | None = None
    edge_ids: list[str] | None = None
    namespace: str = "aqp_bronze_feeds"
    table_name: str | None = None
    medallion_layer: str = "bronze"
    business_metadata: dict[str, Any] | None = None


def _sanitize_feed_segment(value: str) -> str:
    token = re.sub(r"[^a-z0-9_]+", "_", str(value).lower()).strip("_")
    return token or "feed"


def _build_feed_sync_tool(
    *,
    feed_id: str,
    feed_name: str,
) -> type[DataMCPTool]:
    safe_name = _sanitize_feed_segment(feed_name)
    safe_id = _sanitize_feed_segment(feed_id)
    tool_name = f"{_DYNAMIC_FEED_TOOL_PREFIX}{safe_name}_{safe_id}.sync"
    class_name = (
        "FeedSyncTool_"
        f"{safe_name}_{safe_id}_{uuid.uuid5(uuid.NAMESPACE_DNS, feed_id).hex[:8]}"
    )
    description = (
        f"Queue a sync for feed '{feed_name}' ({feed_id}). "
        "Mutates state and returns a Celery task_id."
    )

    def _run(
        self,
        *,
        ctx: MCPToolContext,
        time_window: tuple[str, str] | None = None,
        edge_ids: list[str] | None = None,
        namespace: str = "aqp_bronze_feeds",
        table_name: str | None = None,
        medallion_layer: str = "bronze",
        business_metadata: dict[str, Any] | None = None,
    ) -> MCPToolResult:
        from aqp.tasks.data_sync_tasks import sync_feed

        task = sync_feed.delay(
            feed_id=feed_id,
            time_window=time_window,
            namespace=namespace,
            table_name=table_name or feed_id,
            medallion_layer=medallion_layer,
            business_metadata=business_metadata,
            edge_ids=edge_ids,
        )
        return MCPToolResult(
            ok=True,
            data={"task_id": str(task.id), "feed_id": feed_id},
            summary=f"queued sync for {feed_name}",
        )

    attrs: dict[str, Any] = {
        "name": tool_name,
        "description": description,
        "args_schema": _FeedSyncToolArgs,
        "category": "sources",
        "tags": ("feeds", "sync", "dynamic"),
        "mutates": True,
        "required_scopes": ("data:read", "data:write"),
        "run": _run,
    }
    return type(class_name, (DataMCPTool,), attrs)


def _refresh_feed_tool_catalog(tool_registry: dict[str, type[DataMCPTool]]) -> int:
    """Rebuild dynamic per-feed MCP tools from enabled ``DataSource`` rows."""

    from aqp.persistence.db import get_session
    from aqp.persistence.models import DataSource

    generated: dict[str, type[DataMCPTool]] = {}
    # Materialise the (feed_id, name, enabled) tuples *inside* the session
    # so we don't trigger DetachedInstanceError when reading attributes
    # after the session closes (the session is expire-on-commit by default).
    rows: list[tuple[str, str, bool]] = []
    try:
        with get_session() as session:
            for row in session.query(DataSource).order_by(DataSource.name.asc()).all():
                rows.append((
                    str(getattr(row, "id", "") or ""),
                    str(getattr(row, "name", "") or ""),
                    bool(getattr(row, "enabled", True)),
                ))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to enumerate DataSource rows for MCP feed catalog refresh")
        return 0

    for feed_id, raw_name, enabled in rows:
        if not enabled:
            continue
        if not feed_id:
            continue
        feed_name = raw_name or feed_id
        tool_cls = _build_feed_sync_tool(feed_id=feed_id, feed_name=feed_name)
        generated[tool_cls.name] = tool_cls

    with _DYNAMIC_FEED_LOCK:
        for name in list(_DYNAMIC_FEED_TOOL_NAMES):
            tool_registry.pop(name, None)
        tool_registry.update(generated)
        _DYNAMIC_FEED_TOOL_NAMES.clear()
        _DYNAMIC_FEED_TOOL_NAMES.update(generated.keys())
    return len(generated)


def build_mcp_router() -> APIRouter:
    """Return a FastAPI router exposing the DataMCP tool catalog.

    Authorization:

    - ``GET /mcp/data/tools`` and ``GET /mcp/data/tools/{name}`` are
      discoverable without authentication so SDKs can render the
      catalog before login.
    - ``POST /mcp/data/tools/{name}/invoke`` requires
      :func:`aqp.auth.deps.require_authenticated` and overrides the
      caller-supplied ``actor`` / ``workspace_id`` / ``project_id``
      with the values from the verified JWT + tenancy headers. This
      closes the AGENTS rule 22 gap where an unauthenticated external
      MCP client could forge identity by sending arbitrary body fields.
    """
    router = APIRouter(prefix="/mcp/data", tags=["data-mcp"])
    tool_registry = DATA_MCP_TOOLS

    refreshed = _refresh_feed_tool_catalog(tool_registry)
    logger.info("DataMCP dynamic feed catalog initialised with %d tools", refreshed)

    def _on_feed_event(event: FeedEvent) -> None:
        if event.kind not in {"upsert", "delete", "sync_triggered"}:
            return
        refreshed_count = _refresh_feed_tool_catalog(tool_registry)
        logger.info(
            "DataMCP feed tool catalog refreshed after %s for %s (count=%d)",
            event.kind,
            event.data_source_id,
            refreshed_count,
        )

    global _DYNAMIC_FEED_UNSUBSCRIBE
    if _DYNAMIC_FEED_UNSUBSCRIBE is None:
        _DYNAMIC_FEED_UNSUBSCRIBE = get_feed_event_bus().subscribe(_on_feed_event)

    def _tool_descriptors() -> list[dict[str, Any]]:
        with _DYNAMIC_FEED_LOCK:
            return [
                tool_registry[name].to_mcp_tool_descriptor()
                for name in sorted(tool_registry)
            ]

    def _tool_cls(name: str) -> type[DataMCPTool] | None:
        with _DYNAMIC_FEED_LOCK:
            return tool_registry.get(name)

    @router.get("/tools")
    def list_tools() -> dict[str, Any]:
        tools = _tool_descriptors()
        return {
            "ok": True,
            "tools": tools,
            "count": len(tools),
        }

    @router.get("/tools/{name}")
    def describe_tool(name: str) -> dict[str, Any]:
        cls = _tool_cls(name)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
        return {"ok": True, "tool": cls.to_mcp_tool_descriptor()}

    @router.post("/tools/{name}/invoke")
    def invoke_tool(
        name: str,
        body: MCPInvokeRequest,
        request: Request,
        user: CurrentUser = Depends(require_authenticated),
        ctx: RequestContext = Depends(current_context),
    ) -> dict[str, Any]:
        cls = _tool_cls(name)
        if cls is None:
            raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
        # RFC 8707 audience binding (workstream E). The 2025-11-25 MCP
        # spec requires that access tokens carry the canonical MCP
        # server URI in their ``aud`` (or ``resource``) claim. The
        # validator below is a no-op when ``AQP_MCP_REQUIRE_RFC8707=off``
        # (default during the rollout) and emits OTEL would-deny tags
        # in permissive mode; strict mode raises 401 with the RFC 9728
        # ``WWW-Authenticate`` header pointing at the matching
        # ``/.well-known/oauth-protected-resource/mcp/data`` document.
        validate_mcp_audience(
            request,
            get_data_mcp_canonical_uri(),
            mode=get_mcp_audience_mode(),
        )
        # Tenancy / identity always comes from the verified JWT +
        # X-AQP-* headers, never from the request body. Body fields
        # like ``actor`` are kept only for the ``actor_kind`` /
        # ``session_id`` /``request_id`` metadata which doesn't grant
        # access. The body's ``granted_scopes`` is intersected with the
        # scopes the user is actually allowed to use (today that means
        # we accept whatever the user passes since the auth layer
        # doesn't yet emit a scope list — Phase 4 will tighten this).
        mcp_ctx = MCPToolContext(
            actor=user.id,
            actor_kind=body.actor_kind or "user",
            session_id=body.session_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            granted_scopes=tuple(body.granted_scopes or ("data:read",)),
            request_id=body.request_id,
        )
        tool = cls()
        result = tool.invoke(ctx=mcp_ctx, **(body.arguments or {}))
        return {"ok": result.ok, "result": result.to_json()}

    return router


# ---------------------------------------------------------------------------
# stdio transport
# ---------------------------------------------------------------------------


def _validate_stdio_token() -> dict[str, Any] | None:
    """Validate ``$AQP_M2M_TOKEN`` against the active OIDC tenant.

    Returns the verified JWT claims on success. When OIDC is not
    configured (``auth_provider=local``) returns an empty dict so the
    local dev loop keeps working — the stdio binary is otherwise
    unusable without a token. Returns ``None`` when a token was
    expected but is missing / invalid; callers refuse to start.
    """
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
        with _DYNAMIC_FEED_LOCK:
            tools = [
                DATA_MCP_TOOLS[name].to_mcp_tool_descriptor()
                for name in sorted(DATA_MCP_TOOLS)
            ]
        response = {
            "ok": True,
            "id": request_id,
            "result": {
                "tools": tools,
                "count": len(tools),
            },
        }
    elif method == "tools/describe":
        name = params.get("name")
        with _DYNAMIC_FEED_LOCK:
            tool_cls = DATA_MCP_TOOLS.get(str(name))
        if tool_cls is None:
            response = {
                "ok": False,
                "id": request_id,
                "error": f"unknown tool {name!r}",
            }
        else:
            response = {
                "ok": True,
                "id": request_id,
                "result": tool_cls.to_mcp_tool_descriptor(),
            }
    elif method == "tools/invoke":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        # Identity comes from the verified ``$AQP_M2M_TOKEN`` claims
        # (or the local default in non-OIDC deployments). The body
        # MAY tighten tenancy further (e.g. pin a specific project
        # the M2M token can see), never relax it.
        actor = _stdio_actor()
        ctx = MCPToolContext(
            actor=actor,
            actor_kind=params.get("actor_kind") or "service",
            session_id=params.get("session_id"),
            workspace_id=params.get("workspace_id"),
            project_id=params.get("project_id"),
            granted_scopes=tuple(params.get("granted_scopes") or ("data:read",)),
            request_id=params.get("request_id"),
        )
        with _DYNAMIC_FEED_LOCK:
            tool_cls = DATA_MCP_TOOLS.get(str(name))
        if tool_cls is None:
            response = {
                "ok": False,
                "id": request_id,
                "error": f"unknown tool {name!r}",
            }
        else:
            tool = tool_cls()
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
            "result": {"server": "aqp-data-mcp", "ts": datetime.utcnow().isoformat()},
        }
    else:
        response = {
            "ok": False,
            "id": request_id,
            "error": f"unknown method {method!r}",
        }
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
    """Console-script entry point — runs the stdio MCP transport.

    Registered as ``aqp-data-mcp`` in ``pyproject.toml``. The function
    blocks until stdin is closed.

    Authorization: when ``settings.auth_provider != "local"``, the
    binary validates the ``$AQP_M2M_TOKEN`` env var against the
    configured OIDC tenant. The verified ``sub`` claim becomes the
    actor on every tool invocation. Without a valid token in OIDC mode
    the binary exits with status 2 — external IDEs MUST mint an M2M
    token before launching.
    """
    global _STDIO_AUTH_CLAIMS
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    _STDIO_AUTH_CLAIMS = _validate_stdio_token()
    if _STDIO_AUTH_CLAIMS is None:
        sys.stderr.write(
            "aqp-data-mcp: AQP_M2M_TOKEN is required when auth_provider != 'local'\n"
        )
        return 2
    refreshed = _refresh_feed_tool_catalog(DATA_MCP_TOOLS)
    logger.info(
        "aqp-data-mcp stdio server starting; %d tools registered (actor=%s, dynamic_feeds=%d)",
        len(DATA_MCP_TOOLS),
        _stdio_actor(),
        refreshed,
    )
    try:
        asyncio.run(_stdio_loop())
    except KeyboardInterrupt:
        logger.info("aqp-data-mcp stopped")
    return 0


__all__ = ["build_mcp_router", "run_stdio"]
