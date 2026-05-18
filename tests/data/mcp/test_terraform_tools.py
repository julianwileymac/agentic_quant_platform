"""Tests for the ``data.terraform.*`` DataMCP tools.

Asserts registration + schema declaration + scope enforcement. The
actual DB / runtime interaction is exercised by the integration test
suite (``tests/api/routes/test_terraform.py``).
"""
from __future__ import annotations

from aqp.data.mcp.registry import DATA_MCP_TOOLS, get_data_mcp_tool


def test_terraform_tools_registered():
    expected = {
        "data.terraform.list_workspaces",
        "data.terraform.describe_workspace",
        "data.terraform.list_runs",
        "data.terraform.get_state_outputs",
        "data.terraform.diff_state",
        "data.terraform.lock_status",
        "data.terraform.plan_stack",
        "data.terraform.apply_stack",
        "data.terraform.destroy_stack",
        "data.terraform.cancel_run",
    }
    for name in expected:
        assert name in DATA_MCP_TOOLS, f"{name!r} not registered"


def test_terraform_mutating_tools_carry_correct_scopes():
    plan = get_data_mcp_tool("data.terraform.plan_stack")
    assert plan.mutates is True
    assert "terraform:plan" in plan.required_scopes

    apply = get_data_mcp_tool("data.terraform.apply_stack")
    assert apply.mutates is True
    assert "terraform:apply" in apply.required_scopes

    destroy = get_data_mcp_tool("data.terraform.destroy_stack")
    assert destroy.mutates is True
    assert "terraform:destroy" in destroy.required_scopes


def test_terraform_read_tools_are_not_mutating():
    for name in (
        "data.terraform.list_workspaces",
        "data.terraform.describe_workspace",
        "data.terraform.list_runs",
        "data.terraform.get_state_outputs",
        "data.terraform.diff_state",
        "data.terraform.lock_status",
    ):
        tool = get_data_mcp_tool(name)
        assert tool.mutates is False
        assert "data:read" in tool.required_scopes
