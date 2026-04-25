"""CrewAI tool adapters — the platform's public agent-facing API."""

from aqp.agents.tools.backtest_tool import BacktestTool, WalkForwardTool
from aqp.agents.tools.chroma_tool import ChromaSearchTool, MemoryRecallTool
from aqp.agents.tools.directory_tool import DirectoryReadTool
from aqp.agents.tools.duckdb_tool import DescribeBarsTool, DuckDBQueryTool
from aqp.agents.tools.evaluator_tool import MetricsTool, PlotlyTool
from aqp.agents.tools.fundamentals_tool import FundamentalsTool
from aqp.agents.tools.news_tool import NewsTool
from aqp.agents.tools.rating_tool import RatingTool
from aqp.agents.tools.risk_tool import KillSwitchTool, LedgerTool, RiskCheckTool
from aqp.agents.tools.technical_tool import TechnicalTool


TOOL_REGISTRY: dict[str, type] = {
    "duckdb_query": DuckDBQueryTool,
    "describe_bars": DescribeBarsTool,
    "chroma_search": ChromaSearchTool,
    "memory_recall": MemoryRecallTool,
    "directory_read": DirectoryReadTool,
    "backtest": BacktestTool,
    "walk_forward": WalkForwardTool,
    "risk_check": RiskCheckTool,
    "kill_switch": KillSwitchTool,
    "ledger": LedgerTool,
    "metrics": MetricsTool,
    "plotly": PlotlyTool,
    "technical_snapshot": TechnicalTool,
    "fundamentals_snapshot": FundamentalsTool,
    "news_digest": NewsTool,
    "normalize_rating": RatingTool,
}


def get_tool(name: str):
    """Look up a tool class by name (used by the crew YAML loader)."""
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}. Known: {sorted(TOOL_REGISTRY)}")
    return TOOL_REGISTRY[name]()


__all__ = [
    "BacktestTool",
    "ChromaSearchTool",
    "DescribeBarsTool",
    "DirectoryReadTool",
    "DuckDBQueryTool",
    "FundamentalsTool",
    "KillSwitchTool",
    "LedgerTool",
    "MemoryRecallTool",
    "MetricsTool",
    "NewsTool",
    "PlotlyTool",
    "RatingTool",
    "RiskCheckTool",
    "TechnicalTool",
    "WalkForwardTool",
    "get_tool",
]
