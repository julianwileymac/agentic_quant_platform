"""Smoke tests for the new vbt-pro agent tools — no engine execution."""
from __future__ import annotations

import json

import pytest

from aqp.agents.tools import TOOL_REGISTRY, get_tool


@pytest.mark.parametrize(
    "tool_name",
    [
        "vectorbt_pro_backtest",
        "vectorbt_pro_param_sweep",
        "vectorbt_pro_wfo",
        "vectorbt_pro_optimizer",
        "engine_capabilities",
        "agent_aware_backtest",
    ],
)
def test_vbtpro_tool_registered(tool_name: str) -> None:
    assert tool_name in TOOL_REGISTRY
    instance = get_tool(tool_name)
    assert instance.name == tool_name


def test_engine_capabilities_tool_returns_matrix() -> None:
    tool = get_tool("engine_capabilities")
    payload = tool._run()
    parsed = json.loads(payload)
    assert "EventDrivenBacktester" in parsed
    assert "VectorbtProEngine" in parsed
    assert parsed["EventDrivenBacktester"]["supports_per_bar_python"] is True


def test_engine_capabilities_tool_filters_by_engine() -> None:
    tool = get_tool("engine_capabilities")
    payload = tool._run(engine="VectorbtProEngine")
    parsed = json.loads(payload)
    assert parsed["name"] == "vectorbt-pro"
    assert parsed["supports_signals"] is True


def test_engine_capabilities_unknown_engine_errors() -> None:
    tool = get_tool("engine_capabilities")
    payload = tool._run(engine="NotARealEngine")
    assert "ERROR" in payload
