"""DataMCP tool catalog tests."""
from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from aqp.data.mcp import (
    DATA_MCP_TOOLS,
    DataMCPTool,
    MCPPolicyError,
    MCPToolContext,
    MCPToolResult,
    list_data_mcp_tools,
    register_data_mcp_tool,
)
from aqp.data.mcp.policy import (
    enforce_data_minimization,
    enforce_read_only_for_session,
    enforce_required_scopes,
    enforce_tenancy,
)


class _EchoArgs(BaseModel):
    text: str = Field(...)


@register_data_mcp_tool
class _EchoTool(DataMCPTool):
    name = "tests.echo"
    description = "Echoes its argument."
    args_schema = _EchoArgs
    category = "tests"
    tags = ("tests", "echo")

    def run(self, *, ctx: MCPToolContext, text: str) -> MCPToolResult:
        return MCPToolResult(ok=True, data={"echo": text}, summary=f"echoed {text!r}")


def test_registry_contains_canonical_tools() -> None:
    descriptors = list_data_mcp_tools()
    names = {entry["name"] for entry in descriptors}
    expected = {
        "data.catalog.browse",
        "data.catalog.describe_dataset",
        "data.catalog.profile_dataset",
        "data.catalog.lineage",
        "data.entities.equity",
        "data.entities.option_chain",
        "data.entities.macro_series",
        "data.entities.regulatory",
        "data.entities.portfolio",
        "data.entities.instrument_graph",
        "data.pipelines.list_manifests",
        "data.pipelines.list_runs",
        "data.pipelines.get_run",
        "data.pipelines.run_manifest",
        "data.sinks.list",
        "data.sinks.materialise",
        "data.sources.list",
        "data.sources.get_wizard",
        "data.sources.run_wizard",
        "data.streaming.kafka.list_topics",
        "data.streaming.flink.list_jobs",
        "data.streaming.producers.list",
        "data.iceberg.read_slice",
        "data.iceberg.snapshot_history",
        "data.iceberg.time_travel_read",
        "data.datahub.lookup",
        "data.datahub.sync",
        "data.datahub.sync_log",
    }
    missing = expected - names
    assert not missing, f"missing DataMCP tools: {missing}"


def test_descriptors_carry_required_metadata() -> None:
    for descriptor in list_data_mcp_tools():
        assert descriptor["name"]
        assert descriptor["description"]
        assert descriptor["category"]
        assert "required_scopes" in descriptor
        assert "mutates" in descriptor


def test_policy_required_scopes_rejects_missing() -> None:
    ctx = MCPToolContext(granted_scopes=())
    with pytest.raises(MCPPolicyError):
        enforce_required_scopes(ctx, ("data:read",))


def test_policy_tenancy_rejects_missing_workspace() -> None:
    ctx = MCPToolContext()
    with pytest.raises(MCPPolicyError):
        enforce_tenancy(ctx)
    enforce_tenancy(ctx, required=False)


def test_policy_read_only_rejects_mutating_without_write_scope() -> None:
    ctx = MCPToolContext(granted_scopes=("data:read",))
    enforce_read_only_for_session(ctx, mutates=False)
    with pytest.raises(MCPPolicyError):
        enforce_read_only_for_session(ctx, mutates=True)


def test_policy_data_minimization_rejects_blocked_columns() -> None:
    ctx = MCPToolContext()
    with pytest.raises(MCPPolicyError):
        enforce_data_minimization(
            ctx,
            requested_columns=["close", "ssn"],
            allowed_columns=["close", "volume"],
        )


def test_invoke_runs_tool_and_emits_result() -> None:
    tool = _EchoTool()
    ctx = MCPToolContext(granted_scopes=("data:read",))
    result = tool.invoke(ctx=ctx, text="hello")
    assert result.ok is True
    assert result.data == {"echo": "hello"}
    assert result.elapsed_ms is not None


def test_invoke_validates_args_schema() -> None:
    tool = _EchoTool()
    ctx = MCPToolContext(granted_scopes=("data:read",))
    result = tool.invoke(ctx=ctx, wrong_field="oops")  # missing 'text'
    assert result.ok is False
    assert result.error is not None and "text" in result.error.lower()


def test_invoke_rejects_when_policy_denies() -> None:
    tool = _EchoTool()
    ctx = MCPToolContext(granted_scopes=())
    result = tool.invoke(ctx=ctx, text="hello")
    assert result.ok is False
    assert "policy" in (result.error or "").lower()


def test_descriptor_json_schema_serialises() -> None:
    tool = _EchoTool
    descriptor = tool.to_mcp_tool_descriptor()
    assert descriptor["name"] == "tests.echo"
    assert "inputSchema" in descriptor
    function_schema = tool.to_openai_function()
    assert function_schema["function"]["name"] == "tests.echo"
