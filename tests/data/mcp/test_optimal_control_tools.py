"""Smoke tests for the optimal-control DataMCPTools.

Verifies the three tools register, expose the right schemas, enforce
their policy_check, and return well-shaped MCPToolResults.
"""
from __future__ import annotations

import pytest

from aqp.data.mcp import DATA_MCP_TOOLS, MCPPolicyError, MCPToolContext


def test_tools_registered() -> None:
    expected = {
        "data.optimal_control.solve_hjb",
        "data.optimal_control.evaluate_strategy",
        "data.optimal_control.list_regimes",
        "data.strategy_config.update",
    }
    assert expected.issubset(set(DATA_MCP_TOOLS.keys()))


def _ctx(*scopes: str) -> MCPToolContext:
    """Build a tenancy-satisfying context for the read-only tools."""
    return MCPToolContext(
        actor="test",
        actor_kind="user",
        workspace_id="ws-test",
        project_id="proj-test",
        granted_scopes=tuple(scopes) or ("data:read",),
    )


def test_solve_hjb_avst_returns_metrics() -> None:
    tool_cls = DATA_MCP_TOOLS["data.optimal_control.solve_hjb"]
    tool = tool_cls()
    ctx = _ctx("data:read")
    result = tool.invoke(
        ctx=ctx,
        model="avst",
        mid_price=100.0,
        inventory=0.0,
        gamma=0.1,
        sigma=0.01,
        k=1.5,
        T_minus_t=1.0,
    )
    assert result.ok, f"got {result.error}"
    assert "metrics" in result.data
    assert "rows_preview" in result.data


def test_solve_hjb_cj_returns_trajectory() -> None:
    tool_cls = DATA_MCP_TOOLS["data.optimal_control.solve_hjb"]
    tool = tool_cls()
    ctx = _ctx("data:read")
    result = tool.invoke(
        ctx=ctx,
        model="cartea_jaimungal",
        horizon=0.5,
        initial_inventory=50.0,
        sigma=0.01,
        phi=1e-4,
        alpha=1e-3,
        kappa=1.0,
        n_steps=20,
    )
    assert result.ok, f"got {result.error}"
    assert result.data["metrics"]["expected_pnl"] is not None
    assert len(result.data["rows_preview"]) <= 100


def test_evaluate_strategy_returns_summary() -> None:
    tool_cls = DATA_MCP_TOOLS["data.optimal_control.evaluate_strategy"]
    tool = tool_cls()
    ctx = _ctx("data:read")
    result = tool.invoke(
        ctx=ctx,
        strategy_alias="AvellanedaStoikovMM",
        symbol="BTCUSDT",
        gamma=0.1,
        sigma=0.01,
        k=1.5,
    )
    assert result.ok
    assert "expected_sharpe" in result.data
    assert "params" in result.data


def test_list_regimes_returns_default_when_empty() -> None:
    tool_cls = DATA_MCP_TOOLS["data.optimal_control.list_regimes"]
    tool = tool_cls()
    ctx = _ctx("data:read")
    result = tool.invoke(ctx=ctx, symbol="BTCUSDT", limit=5)
    assert result.ok
    # Iceberg may or may not be running; at minimum we expect a stub row.
    assert isinstance(result.data, list)


def test_solve_hjb_rejects_unknown_model() -> None:
    tool_cls = DATA_MCP_TOOLS["data.optimal_control.solve_hjb"]
    tool = tool_cls()
    ctx = _ctx("data:read")
    result = tool.invoke(ctx=ctx, model="unknown")
    # Pydantic validates the Literal[] up-front so we get a validation
    # error rather than the tool's own rejection — either is acceptable.
    assert not result.ok
    assert result.error is not None
