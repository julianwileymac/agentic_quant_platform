"""Tests for ``data.strategy_config.update`` controlled-write tool.

Hermetic: writes to a tmp ``configs/paper`` dir, verifies the
whitelist enforcement and the YAML mutation.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aqp.data.mcp import DATA_MCP_TOOLS, MCPToolContext


def test_update_whitelisted_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper_dir = tmp_path / "configs" / "paper"
    paper_dir.mkdir(parents=True)
    cfg = paper_dir / "test.yaml"
    cfg.write_text(
        yaml.safe_dump({"strategy": {"gamma": 0.1, "order_size": 1.0}}),
        encoding="utf-8",
    )

    # Patch the resolver to point at our tmp dir.
    from aqp.data.mcp.tools import strategy_config

    monkeypatch.setattr(strategy_config, "_resolve_paper_dir", lambda: paper_dir)

    tool = DATA_MCP_TOOLS["data.strategy_config.update"]()
    ctx = MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-test",
        project_id="proj-test",
        granted_scopes=("data:read", "strategy:write"),
    )
    result = tool.invoke(
        ctx=ctx,
        config_path="test.yaml",
        field_path="strategy.gamma",
        new_value=0.15,
        reason="unit test",
    )
    assert result.ok, f"got {result.error}"
    contents = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert contents["strategy"]["gamma"] == 0.15


def test_reject_non_whitelisted_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper_dir = tmp_path / "configs" / "paper"
    paper_dir.mkdir(parents=True)
    (paper_dir / "test.yaml").write_text(
        yaml.safe_dump({"broker": {"key": "old"}}),
        encoding="utf-8",
    )

    from aqp.data.mcp.tools import strategy_config

    monkeypatch.setattr(strategy_config, "_resolve_paper_dir", lambda: paper_dir)

    tool = DATA_MCP_TOOLS["data.strategy_config.update"]()
    ctx = MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-test",
        project_id="proj-test",
        granted_scopes=("data:read", "strategy:write"),
    )
    result = tool.invoke(
        ctx=ctx,
        config_path="test.yaml",
        field_path="broker.key",
        new_value=999.0,
    )
    assert not result.ok
    assert "whitelist" in result.error


def test_reject_path_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paper_dir = tmp_path / "configs" / "paper"
    paper_dir.mkdir(parents=True)
    sibling = tmp_path / "configs" / "secrets"
    sibling.mkdir()
    (sibling / "secret.yaml").write_text(
        yaml.safe_dump({"strategy": {"gamma": 0.1}}),
        encoding="utf-8",
    )

    from aqp.data.mcp.tools import strategy_config

    monkeypatch.setattr(strategy_config, "_resolve_paper_dir", lambda: paper_dir)

    tool = DATA_MCP_TOOLS["data.strategy_config.update"]()
    ctx = MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-test",
        project_id="proj-test",
        granted_scopes=("data:read", "strategy:write"),
    )
    result = tool.invoke(
        ctx=ctx,
        config_path="../secrets/secret.yaml",
        field_path="strategy.gamma",
        new_value=999.0,
    )
    assert not result.ok
    assert "escapes" in result.error or "configs/paper" in result.error
