"""Tests for the data.datahub.aspect_sync DataMCP tool."""
from __future__ import annotations

from typing import Any

from aqp.data.mcp.base import MCPToolContext
from aqp.data.mcp.tools import datahub as datahub_tools


def test_aspect_sync_tool_push_direction(monkeypatch) -> None:
    """Push direction delegates to push_aspect and returns ok=True."""
    captured: list[dict[str, Any]] = []

    def _fake_push_aspect(*, urn: str, aspect_name: str | None = None, version: int | None = None) -> dict[str, Any]:
        _ = version
        captured.append({"urn": urn, "aspect_name": aspect_name})
        return {"emitted": True, "n_aspects": 1, "errors": []}

    monkeypatch.setattr(datahub_tools, "push_aspect", _fake_push_aspect)
    tool = datahub_tools.AspectSyncDatahubTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read", "data:write")),
        direction="push",
        urn="urn:aqp:dataset:prod:prices.daily",
        aspect_name="datasetProperties",
    )

    assert result.ok is True
    assert captured and captured[0]["urn"] == "urn:aqp:dataset:prod:prices.daily"


def test_aspect_sync_tool_pull_direction(monkeypatch) -> None:
    """Pull direction delegates to pull_all_aspects and returns ok=True."""
    captured: list[str] = []

    def _fake_pull_all_aspects(*, datahub_urn: str) -> dict[str, Any]:
        captured.append(datahub_urn)
        return {
            "pulled": True,
            "pulled_count": 2,
            "datahub_urn": datahub_urn,
            "errors": [],
            "results": [],
        }

    monkeypatch.setattr(datahub_tools, "pull_all_aspects", _fake_pull_all_aspects)
    tool = datahub_tools.AspectSyncDatahubTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read", "data:write")),
        direction="pull",
        urn="urn:aqp:mlmodel:prod:lstm_v1",
    )

    assert result.ok is True
    assert captured and captured[0].startswith("urn:li:mlModel:")


def test_aspect_sync_tool_requires_data_write_scope() -> None:
    """Mutating sync is denied without data:write scope."""
    tool = datahub_tools.AspectSyncDatahubTool()
    result = tool.invoke(
        ctx=MCPToolContext(granted_scopes=("data:read",)),
        direction="push",
        urn="urn:aqp:dataset:prod:prices.daily",
    )
    assert result.ok is False
    assert "policy denied" in (result.error or "").lower()
