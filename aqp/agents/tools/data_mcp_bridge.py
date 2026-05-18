"""Bridge from :class:`aqp.data.mcp.DataMCPTool` to ``crewai.tools.BaseTool``.

Wraps each registered :class:`DataMCPTool` so it slots into
:data:`aqp.agents.tools.TOOL_REGISTRY` unchanged. AgentRuntime's
existing OpenAI-function-calling loop then dispatches to the same
DataMCP tools as the external MCP server, guaranteeing a single
catalog with two transports.

Tenancy: the bridge reads the active :class:`RequestContext` from
:mod:`aqp.auth.contextvars` and forwards ``workspace_id`` /
``project_id`` into the :class:`MCPToolContext` so the existing
``enforce_tenancy`` policy on each tool actually has data to enforce
on. Without this, agent-driven calls were arriving with an empty
context and tools that required tenancy (sinks, pipeline runs, the
portfolio entity tool) rejected every invocation.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from aqp.auth.contextvars import current_request_context
from aqp.data.mcp import DATA_MCP_TOOLS, MCPToolContext, get_data_mcp_tool

logger = logging.getLogger(__name__)


try:  # pragma: no cover - exercised when CrewAI is installed.
    from crewai.tools import BaseTool as _CrewAIBaseTool  # type: ignore
except ImportError:  # pragma: no cover - dev-only path
    # Fall back to whichever shim aqp.agents.tools.__init__ already
    # installed.
    from aqp.agents.tools import BaseTool as _CrewAIBaseTool  # type: ignore[attr-defined]


def _resolve_mcp_context(extra_scopes: tuple[str, ...] = ()) -> MCPToolContext:
    """Build the MCP tool context from the active :class:`RequestContext`.

    Falls back to a minimal context (no workspace) when nothing is
    bound — those calls will be rejected by tools that require
    tenancy, which is the desired behaviour: an agent invoking a
    write-only tool outside a request lifecycle should not silently
    succeed.

    ``extra_scopes`` carries the spec-declared scopes from
    :class:`aqp.agents.spec.ToolRef.scopes` so mutating tools require
    an explicit, auditable opt-in (defect 4 fix). The default grant
    stays ``("data:read",)`` — a tool that needs ``data:write`` MUST
    have ``scopes: ["data:write"]`` declared in the YAML spec.
    """
    ctx = current_request_context.get()
    workspace_id = getattr(ctx, "workspace_id", None) if ctx is not None else None
    project_id = getattr(ctx, "project_id", None) if ctx is not None else None
    user_id = getattr(ctx, "user_id", None) if ctx is not None else None
    granted = tuple({"data:read", *extra_scopes})
    return MCPToolContext(
        actor=user_id or "agent_runtime",
        actor_kind="agent",
        workspace_id=workspace_id,
        project_id=project_id,
        granted_scopes=granted,
    )


def make_bridge_tool_class(
    mcp_tool_name: str, *, default_scopes: tuple[str, ...] = ()
) -> type:
    """Produce a ``BaseTool`` subclass that delegates to a DataMCPTool.

    The returned class has the same ``name``, ``description``, and
    ``args_schema`` as the underlying :class:`DataMCPTool`. ``_run``
    instantiates a fresh tool, calls :meth:`DataMCPTool.invoke` with
    the validated kwargs, and returns the JSON-serialised
    :class:`MCPToolResult`. AgentRuntime's tool dispatch loop already
    expects a string-shaped return so this fits cleanly.

    ``default_scopes`` is forwarded to :func:`_resolve_mcp_context` so
    the bridge factory can pre-bind spec-time scope grants from
    :attr:`aqp.agents.spec.ToolRef.scopes`. Re-instantiated bridges
    (``cls(scopes=[...])``) override via the kwarg path on the bridge
    class. Read-only tools that don't pass ``scopes`` keep the
    ``("data:read",)`` default and never touch ``data:write``.

    Note on local names: we use ``_tool_name`` / ``_tool_desc`` /
    ``_tool_schema`` instead of ``name`` / ``description`` /
    ``args_schema`` to avoid the Python ≥3.13 scoping bug where the
    class body annotation ``description: str = description`` raises
    ``NameError`` because the class scope does not see the enclosing
    function variable when the annotation and the RHS share a name.
    """
    if mcp_tool_name not in DATA_MCP_TOOLS:
        raise KeyError(f"unknown DataMCPTool {mcp_tool_name!r}")
    cls = DATA_MCP_TOOLS[mcp_tool_name]
    _tool_name = cls.name
    _tool_desc = (cls.description or "").strip()
    _tool_schema = cls.args_schema
    _tool_default_scopes = tuple(default_scopes)
    bridge_class_name = f"DataMCP_{cls.__name__}_Bridge"

    class _BridgeTool(_CrewAIBaseTool):  # type: ignore[misc, valid-type]
        name: str = _tool_name
        description: str = _tool_desc
        args_schema: type[BaseModel] | None = _tool_schema

        def __init__(self, **init_kwargs: Any) -> None:
            scopes = init_kwargs.pop("scopes", None)
            super().__init__(**init_kwargs)
            self._spec_scopes: tuple[str, ...] = (
                tuple(scopes) if scopes is not None else _tool_default_scopes
            )

        def _run(self, **kwargs: Any) -> str:  # type: ignore[override]
            tool = get_data_mcp_tool(mcp_tool_name)
            extra = getattr(self, "_spec_scopes", _tool_default_scopes)
            ctx = _resolve_mcp_context(tuple(extra))
            result = tool.invoke(ctx=ctx, **kwargs)
            try:
                return json.dumps(result.to_json(), default=str)
            except Exception:  # noqa: BLE001
                return json.dumps(
                    {"ok": False, "error": "result serialization failed"}
                )

    _BridgeTool.__name__ = bridge_class_name
    _BridgeTool.__qualname__ = bridge_class_name
    return _BridgeTool


def install_data_mcp_tools(target_registry: dict[str, type]) -> list[str]:
    """Wrap every :class:`DataMCPTool` and merge into ``target_registry``.

    Idempotent: re-registering an existing alias replaces the wrapper
    only if the underlying class differs. Returns the list of tool
    names installed.
    """
    installed: list[str] = []
    for name in sorted(DATA_MCP_TOOLS):
        try:
            wrapper = make_bridge_tool_class(name)
        except Exception:  # noqa: BLE001
            logger.exception("failed to bridge DataMCPTool %s", name)
            continue
        target_registry[name] = wrapper
        installed.append(name)
    return installed


__all__ = ["install_data_mcp_tools", "make_bridge_tool_class", "_resolve_mcp_context"]
