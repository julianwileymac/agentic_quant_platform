"""FinAgent toolset — KlinePlotter, TradingPlotter, StrategyAgentsTool.

These tools are CrewAI ``BaseTool`` subclasses that the FinAgent
LayeredReflectionAdapter cascade can invoke to enrich its prompts
with visualised market context.

All tools register through AQP's :data:`TOOL_REGISTRY` so spec-driven
agents can declare them by name in their YAML
(:attr:`AgentSpec.tools`).
"""
from __future__ import annotations

from aqp.agents.tools.finagent.kline_plotter import KlinePlotterTool
from aqp.agents.tools.finagent.strategy_agents_tool import StrategyAgentsTool
from aqp.agents.tools.finagent.trading_plotter import TradingPlotterTool

__all__ = [
    "KlinePlotterTool",
    "StrategyAgentsTool",
    "TradingPlotterTool",
]
