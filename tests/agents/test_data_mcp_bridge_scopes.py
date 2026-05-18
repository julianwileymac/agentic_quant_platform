"""Regression test for defect 4: DataMCP write scopes from spec.

Before the fix, :func:`aqp.agents.tools.data_mcp_bridge._resolve_mcp_context`
accepted ``extra_scopes`` but the bridge factory never threaded any
spec-time scopes into it, so :class:`MCPToolContext.granted_scopes`
was always exactly ``("data:read",)``. Mutating tools could never run
because :func:`enforce_read_only_for_session` rejected every call.

The fix adds :attr:`aqp.agents.spec.ToolRef.scopes` as a typed list,
the bridge factory records ``default_scopes`` per tool class, and the
tool ``__init__`` accepts ``scopes=[...]`` so :class:`AgentRuntime`'s
``_resolve_tools()`` can pass spec-declared grants.
"""
from __future__ import annotations

from typing import Any

import pytest

from aqp.agents.spec import AgentSpec, ToolRef
from aqp.data.mcp.base import (
    DataMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
)
from aqp.data.mcp.policy import enforce_read_only_for_session


class _StubMutatingTool(DataMCPTool):
    name = "test.mutating_tool"
    description = "Test tool that requires data:write."
    args_schema = None
    mutates = True
    required_scopes = ("data:read", "data:write")

    def policy_check(self, ctx: MCPToolContext) -> None:
        super().policy_check(ctx)
        enforce_read_only_for_session(ctx, mutates=self.mutates)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        return MCPToolResult(ok=True, data={"called": True})


def test_tool_ref_scopes_default_empty():
    ref = ToolRef(name="anything")
    assert ref.scopes == []


def test_tool_ref_scopes_round_trip():
    ref = ToolRef(name="any", scopes=["data:write", "data:admin"])
    assert ref.scopes == ["data:write", "data:admin"]


def test_resolve_mcp_context_default_grants_only_read():
    """Without ``extra_scopes``, only ``data:read`` is granted."""
    from aqp.agents.tools.data_mcp_bridge import _resolve_mcp_context

    ctx = _resolve_mcp_context()
    assert "data:read" in ctx.granted_scopes
    assert "data:write" not in ctx.granted_scopes


def test_resolve_mcp_context_passes_extra_scopes():
    """``extra_scopes`` is merged with the default ``data:read`` grant."""
    from aqp.agents.tools.data_mcp_bridge import _resolve_mcp_context

    ctx = _resolve_mcp_context(("data:write",))
    assert "data:read" in ctx.granted_scopes
    assert "data:write" in ctx.granted_scopes


def test_mutating_tool_rejects_without_spec_scope():
    """Default bridge grant is read-only — mutating tool must reject."""
    tool = _StubMutatingTool()
    ctx = MCPToolContext(granted_scopes=("data:read",))
    with pytest.raises(MCPPolicyError):
        tool.policy_check(ctx)


def test_mutating_tool_accepts_with_spec_scope():
    """Granting ``data:write`` (e.g. via ``ToolRef.scopes``) clears policy."""
    tool = _StubMutatingTool()
    ctx = MCPToolContext(granted_scopes=("data:read", "data:write"))
    tool.policy_check(ctx)  # must not raise
    result = tool.invoke(ctx=ctx)
    assert result.ok is True
    assert result.data == {"called": True}


def test_agent_spec_threads_tool_ref_scopes_into_bridge(monkeypatch):
    """``AgentRuntime._resolve_tools`` passes ``scopes`` to the bridge ctor.

    Stubs ``TOOL_REGISTRY`` with a class whose ``__init__`` records the
    ``scopes`` kwarg so we can assert the runtime forwards
    ``ToolRef.scopes`` verbatim.
    """
    from aqp.agents.runtime import AgentRuntime

    captured: list[Any] = []

    class _ScopeRecorder:
        name = "scope_recorder"
        description = ""
        args_schema = None

        def __init__(self, **kwargs: Any) -> None:
            captured.append(kwargs)

        def _run(self, **_: Any) -> str:
            return "ok"

    monkeypatch.setattr(
        "aqp.agents.tools.TOOL_REGISTRY",
        {"scope_recorder": _ScopeRecorder},
        raising=False,
    )

    spec = AgentSpec(
        name="defect4.scope_threading",
        role="tester",
        tools=[ToolRef(name="scope_recorder", scopes=["data:write"])],
    )
    runtime = AgentRuntime(spec)
    runtime._resolve_tools()

    assert captured, "tool init was never called"
    assert captured[0].get("scopes") == ["data:write"], captured[0]


def test_agent_spec_drops_scope_when_tool_rejects_kwarg(monkeypatch):
    """Legacy tools that don't accept ``scopes`` still instantiate cleanly."""
    from aqp.agents.runtime import AgentRuntime

    class _LegacyTool:
        name = "legacy_no_scopes"
        description = ""
        args_schema = None

        def __init__(self) -> None:  # No **kwargs accepted.
            self.initialized = True

        def _run(self, **_: Any) -> str:
            return "ok"

    monkeypatch.setattr(
        "aqp.agents.tools.TOOL_REGISTRY",
        {"legacy_no_scopes": _LegacyTool},
        raising=False,
    )

    spec = AgentSpec(
        name="defect4.legacy_drop",
        role="tester",
        tools=[ToolRef(name="legacy_no_scopes", scopes=["data:write"])],
    )
    runtime = AgentRuntime(spec)
    tools = runtime._resolve_tools()
    assert len(tools) == 1
    assert getattr(tools[0], "initialized", False) is True
