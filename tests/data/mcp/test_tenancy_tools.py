"""Tests for the ``data.tenancy.*`` DataMCP tools.

Asserts registration + schema declaration + scope enforcement.
"""
from __future__ import annotations

from aqp.data.mcp.registry import DATA_MCP_TOOLS, get_data_mcp_tool


def test_tenancy_tools_registered():
    expected = {
        "data.tenancy.list_organizations",
        "data.tenancy.create_organization",
        "data.tenancy.invite_user",
        "data.tenancy.link_org_to_entra_tenant",
        "data.tenancy.list_memberships",
        "data.tenancy.grant_role",
        "data.tenancy.transfer_resources",
    }
    for name in expected:
        assert name in DATA_MCP_TOOLS, f"{name!r} not registered"


def test_admin_tools_require_admin_scope():
    for name in (
        "data.tenancy.create_organization",
        "data.tenancy.link_org_to_entra_tenant",
        "data.tenancy.grant_role",
        "data.tenancy.transfer_resources",
    ):
        tool = get_data_mcp_tool(name)
        assert tool.mutates is True
        assert "tenancy:admin" in tool.required_scopes


def test_invite_tool_requires_invite_scope():
    tool = get_data_mcp_tool("data.tenancy.invite_user")
    assert tool.mutates is True
    assert "tenancy:invite" in tool.required_scopes


def test_read_tools_use_data_read_scope():
    for name in (
        "data.tenancy.list_organizations",
        "data.tenancy.list_memberships",
    ):
        tool = get_data_mcp_tool(name)
        assert tool.mutates is False
        assert "data:read" in tool.required_scopes
