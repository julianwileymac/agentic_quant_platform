"""TOOL_REGISTRY bridge and external MCP server tests."""
from __future__ import annotations

import json

import pytest

from aqp.data.mcp import DATA_MCP_TOOLS


def test_bridge_installs_tools_into_registry() -> None:
    pytest.importorskip("aqp.agents.tools")
    from aqp.agents.tools import TOOL_REGISTRY

    expected_aliases = list(DATA_MCP_TOOLS.keys())
    missing = [name for name in expected_aliases if name not in TOOL_REGISTRY]
    assert not missing, f"bridge missed tools: {missing}"


def test_bridge_wrappers_carry_correct_metadata() -> None:
    pytest.importorskip("aqp.agents.tools")
    from aqp.agents.tools.data_mcp_bridge import make_bridge_tool_class

    cls = make_bridge_tool_class("data.catalog.browse")
    assert getattr(cls, "name", None) == "data.catalog.browse"
    assert "browse" in (getattr(cls, "description", "") or "").lower()


def test_mcp_server_router_lists_and_describes_tools() -> None:
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.data.mcp.server import build_mcp_router

    app = FastAPI()
    app.include_router(build_mcp_router())
    client = TestClient(app)

    response = client.get("/mcp/data/tools")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] >= len(DATA_MCP_TOOLS)
    assert any(tool["name"] == "data.catalog.browse" for tool in payload["tools"])

    response = client.get("/mcp/data/tools/data.catalog.browse")
    assert response.status_code == 200
    body = response.json()
    assert body["tool"]["name"] == "data.catalog.browse"

    response = client.get("/mcp/data/tools/does.not.exist")
    assert response.status_code == 404


def test_mcp_server_invoke_runs_through_policy_check() -> None:
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from aqp.data.mcp.server import build_mcp_router

    app = FastAPI()
    app.include_router(build_mcp_router())
    client = TestClient(app)

    response = client.post(
        "/mcp/data/tools/data.iceberg.snapshot_history/invoke",
        json={
            "arguments": {"iceberg_identifier": "aqp_silver_alpha_vantage.daily_bars"},
            "granted_scopes": [],  # no data:read scope
        },
    )
    body = response.json()
    # Policy should deny the call when no scopes granted.
    assert body["ok"] is False
    assert "policy" in (body["result"]["error"] or "").lower()


def test_mcp_stdio_handler_responds_to_ping() -> None:
    import asyncio

    from aqp.data.mcp.server import _handle_stdio_line

    response = asyncio.run(_handle_stdio_line(json.dumps({"id": 1, "method": "ping"})))
    assert response["ok"] is True
    assert response["result"]["server"] == "aqp-data-mcp"


def test_mcp_stdio_handler_lists_tools() -> None:
    import asyncio

    from aqp.data.mcp.server import _handle_stdio_line

    response = asyncio.run(
        _handle_stdio_line(json.dumps({"id": 7, "method": "tools/list"}))
    )
    assert response["ok"] is True
    assert response["result"]["count"] >= len(DATA_MCP_TOOLS)
