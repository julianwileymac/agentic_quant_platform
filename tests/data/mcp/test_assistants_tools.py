"""``data.assistants.*`` MCP tool tests.

Verifies the four tools degrade cleanly when the Phase 2
``assistant_*`` tables aren't provisioned and that the listing /
describe paths round-trip the registry.
"""
from __future__ import annotations

import pytest

from aqp.assistants.registry import (
    add_assistant_spec,
    clear_assistant_registry,
)
from aqp.assistants.spec import AssistantSpec
from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools.assistants import (
    AssistantHealthTool,
    DescribeAssistantTool,
    GetAssistantRunTool,
    ListAssistantsTool,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_assistant_registry()


def _ctx() -> MCPToolContext:
    return MCPToolContext(granted_scopes=("data:read",), workspace_id=None)


def test_list_assistants_returns_registered():
    add_assistant_spec(
        AssistantSpec(
            name="t.platform",
            mode="agent",
            agent_spec_name="codebase_assistant",
            description="t",
        )
    )
    tool = ListAssistantsTool()
    res = tool.invoke(ctx=_ctx())
    assert res.ok is True
    names = [item["name"] for item in res.data]
    assert "t.platform" in names


def test_describe_assistant_returns_full_payload():
    spec = AssistantSpec(
        name="t.describe",
        mode="agent",
        agent_spec_name="codebase_assistant",
    )
    add_assistant_spec(spec)
    tool = DescribeAssistantTool()
    res = tool.invoke(ctx=_ctx(), name="t.describe")
    assert res.ok is True
    assert res.data["name"] == "t.describe"
    assert res.data["agent_spec_name"] == "codebase_assistant"


def test_describe_assistant_unknown_returns_error():
    tool = DescribeAssistantTool()
    res = tool.invoke(ctx=_ctx(), name="nope")
    assert res.ok is False
    assert "nope" in (res.error or "")


def test_assistant_health_degrades_when_table_missing(monkeypatch):
    """Force the import of ``assistant_runs`` to fail so we exercise
    the degraded path."""
    import aqp.data.mcp.tools.assistants as mod

    real_import = __import__

    def _block(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "aqp.persistence.models_assistants":
            raise ImportError("simulated table missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _block)
    res = mod.AssistantHealthTool().invoke(ctx=_ctx())
    assert res.ok is True
    assert res.data["table_present"] is False


def test_get_assistant_run_degrades_when_table_missing(monkeypatch):
    import aqp.data.mcp.tools.assistants as mod

    real_import = __import__

    def _block(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "aqp.persistence.models_assistants":
            raise ImportError("simulated table missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _block)
    res = mod.GetAssistantRunTool().invoke(ctx=_ctx(), run_id="abc")
    assert res.ok is True
    assert res.data["table_present"] is False
