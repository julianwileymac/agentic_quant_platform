"""AgentCore Gateway bridge smoke test (Phase E of AWS hybrid).

Verifies that :class:`BedrockAgentCoreGatewayBridge.render`:

1. Reads every registered :class:`DataMCPTool` (no boto3 required).
2. Emits an entry per tool with ``name`` / ``description`` /
   ``input_schema`` / ``mutates`` / ``required_scopes`` /
   ``transport`` / ``invoke_url``.
3. Filters mutating tools when ``include_mutating=False``.
4. Computes a stable catalog hash (same registry -> same hash).
"""
from __future__ import annotations

from aqp.agents.tools.bedrock_agentcore_gateway import (
    BedrockAgentCoreGatewayBridge,
)
from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.registry import register_data_mcp_tool
from pydantic import BaseModel, Field


class _SmokeReadInput(BaseModel):
    workspace_id: str = Field(..., min_length=1)


@register_data_mcp_tool
class _SmokeReadTool(DataMCPTool):
    name = "data.test.smoke_read"
    description = "Smoke read tool — returns a static OK."
    args_schema = _SmokeReadInput
    required_scopes = ("data:read",)
    mutates = False

    def run(self, *, ctx: MCPToolContext, workspace_id: str):  # noqa: D401
        return MCPToolResult(ok=True, data={"workspace_id": workspace_id})


class _SmokeMutateInput(BaseModel):
    workspace_id: str
    payload: dict = Field(default_factory=dict)


@register_data_mcp_tool
class _SmokeMutateTool(DataMCPTool):
    name = "data.test.smoke_mutate"
    description = "Smoke mutating tool — returns OK."
    args_schema = _SmokeMutateInput
    required_scopes = ("data:write",)
    mutates = True

    def run(self, *, ctx: MCPToolContext, workspace_id: str, payload=None):  # noqa: D401
        return MCPToolResult(ok=True, data={"applied": True})


def test_bridge_renders_every_registered_tool():
    bridge = BedrockAgentCoreGatewayBridge(environment="dev")
    cfg = bridge.render()
    names = {entry["name"] for entry in cfg.tools}
    assert "data.test.smoke_read" in names
    assert "data.test.smoke_mutate" in names


def test_bridge_excludes_mutating_when_opted_out():
    bridge = BedrockAgentCoreGatewayBridge(environment="dev")
    cfg = bridge.render(include_mutating=False)
    names = {entry["name"] for entry in cfg.tools}
    assert "data.test.smoke_read" in names
    assert "data.test.smoke_mutate" not in names


def test_bridge_entry_has_required_fields():
    bridge = BedrockAgentCoreGatewayBridge(environment="dev")
    cfg = bridge.render()
    entry = next(e for e in cfg.tools if e["name"] == "data.test.smoke_read")
    for required in (
        "name",
        "description",
        "input_schema",
        "mutates",
        "required_scopes",
        "transport",
        "invoke_url",
    ):
        assert required in entry
    assert entry["transport"] == "aqp-data-mcp"
    assert entry["invoke_url"].endswith("/invoke")
    assert entry["mutates"] is False


def test_catalog_hash_is_stable_across_calls():
    bridge_a = BedrockAgentCoreGatewayBridge(environment="dev")
    bridge_b = BedrockAgentCoreGatewayBridge(environment="dev")
    assert bridge_a.render().catalog_hash() == bridge_b.render().catalog_hash()
