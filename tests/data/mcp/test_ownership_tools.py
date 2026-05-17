"""Tests for the Phase 3 ``data.ownership.*`` / ``data.experiments.*`` /
``data.tests.*`` MCP tools.

We mock :func:`aqp.graph.get_ownership_store` to avoid spinning up a
real Neo4j; the same surface is exercised on a real store by the
Phase 9 smoke test.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from aqp.data.mcp.base import MCPToolContext
from aqp.graph.protocol import OwnershipEdge, OwnershipNode


@pytest.fixture
def fake_ownership_store(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    store = MagicMock()
    store.name = "fake"
    monkeypatch.setattr("aqp.data.mcp.tools.ownership.get_ownership_store", lambda: store)
    return store


def test_ownership_tree_passes_args(fake_ownership_store: MagicMock) -> None:
    from aqp.data.mcp.tools.ownership import OwnershipTreeTool

    fake_ownership_store.traverse.return_value = {
        "nodes": [{"id": "ws-1", "kind": "Workspace"}],
        "edges": [],
    }
    tool = OwnershipTreeTool()
    result = tool.invoke(
        ctx=MCPToolContext(actor="u1", granted_scopes=("data:read",)),
        start_kind="Workspace",
        start_id="ws-1",
        edge_kinds=["HAS_PROJECT"],
        depth=3,
    )
    assert result.ok is True
    fake_ownership_store.traverse.assert_called_once_with(
        start_kind="Workspace",
        start_id="ws-1",
        edge_kinds=["HAS_PROJECT"],
        depth=3,
        limit=200,
    )


def test_list_resources_uses_ctx_actor_when_user_id_omitted(
    fake_ownership_store: MagicMock,
) -> None:
    from aqp.data.mcp.tools.ownership import ListResourcesVisibleTool

    fake_ownership_store.list_resources_visible_to.return_value = [
        OwnershipNode(id="r1", kind="Resource", properties={"name": "Foo"})
    ]
    tool = ListResourcesVisibleTool()
    result = tool.invoke(
        ctx=MCPToolContext(actor="user-7", granted_scopes=("data:read",)),
        resource_type="strategy_template",
    )
    assert result.ok is True
    assert result.rows_returned == 1
    fake_ownership_store.list_resources_visible_to.assert_called_once_with(
        user_id="user-7",
        resource_type="strategy_template",
        limit=200,
    )


def test_list_resources_rejects_when_no_user(fake_ownership_store: MagicMock) -> None:
    from aqp.data.mcp.tools.ownership import ListResourcesVisibleTool

    tool = ListResourcesVisibleTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),  # no actor / no user_id
    )
    assert result.ok is False
    assert "user_id" in (result.error or "")


def test_who_can_read_returns_membership_rows(fake_ownership_store: MagicMock) -> None:
    from aqp.data.mcp.tools.ownership import WhoCanReadTool

    fake_ownership_store.who_can_read.return_value = [
        {"user_id": "u1", "role": "owner", "scope_kind": "workspace", "scope_id": "ws-1"}
    ]
    tool = WhoCanReadTool()
    result = tool.invoke(
        ctx=MCPToolContext(actor="u1", granted_scopes=("data:read",)),
        resource_id="r1",
    )
    assert result.ok is True
    assert result.data == [
        {"user_id": "u1", "role": "owner", "scope_kind": "workspace", "scope_id": "ws-1"}
    ]
