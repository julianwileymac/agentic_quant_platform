"""Hermetic tests for the ``data.ml.*`` DataMCPTool catalog.

The tools register at import time. We assert that the expected names
are present + that the descriptor surface (args_schema, mutates,
category) matches the boundary contract.

Network-bearing calls (HuggingFace / TorchHub pull) are NOT exercised
here — the adapter registry tests cover the guard rails.
"""
from __future__ import annotations

import pytest

# Importing the module registers every tool via the metaclass / decorator.
from aqp.data.mcp import tools as _tools_pkg  # noqa: F401
from aqp.data.mcp.registry import DATA_MCP_TOOLS


EXPECTED_ML_TOOLS = {
    "data.ml.models.list",
    "data.ml.models.describe",
    "data.ml.deployments.list",
    "data.ml.predict",
    "data.ml.forecast",
    "data.ml.classify",
    "data.ml.segment",
    "data.ml.analyze",
    "data.ml.models.pull_huggingface",
    "data.ml.models.pull_torchhub",
    "data.ml.skills.list",
    "data.ml.skills.run",
    "data.ml.compile",
    "data.ml.serving.list",
}


@pytest.mark.parametrize("name", sorted(EXPECTED_ML_TOOLS))
def test_tool_is_registered(name: str) -> None:
    assert name in DATA_MCP_TOOLS, f"{name} missing from DATA_MCP_TOOLS"


def test_pull_tools_declare_data_write_scope() -> None:
    for name in ("data.ml.models.pull_huggingface", "data.ml.models.pull_torchhub"):
        cls = DATA_MCP_TOOLS[name]
        assert "data:write" in cls.required_scopes
        assert cls.mutates is True


def test_predict_tool_has_args_schema() -> None:
    cls = DATA_MCP_TOOLS["data.ml.predict"]
    assert cls.args_schema is not None
    schema = cls.args_schema.model_json_schema()
    assert "model_alias" in schema.get("properties", {})


def test_descriptor_round_trip_is_serialisable() -> None:
    import json

    for name in sorted(EXPECTED_ML_TOOLS):
        cls = DATA_MCP_TOOLS[name]
        descriptor = cls.to_mcp_tool_descriptor()
        # MCP descriptors MUST be JSON-serialisable per the spec.
        json.dumps(descriptor)
        assert descriptor["category"] == "ml"
