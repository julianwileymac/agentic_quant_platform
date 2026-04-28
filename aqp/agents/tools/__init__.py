"""CrewAI tool adapters — the platform's public agent-facing API."""

from aqp.agents.tools.annotation_tool import AnnotationTool
from aqp.agents.tools.backtest_tool import BacktestTool, WalkForwardTool
from aqp.agents.tools.backtrader_tool import BacktraderTool
from aqp.agents.tools.chroma_tool import ChromaSearchTool, MemoryRecallTool
from aqp.agents.tools.directory_tool import DirectoryReadTool
from aqp.agents.tools.duckdb_tool import DescribeBarsTool, DuckDBQueryTool
from aqp.agents.tools.evaluator_tool import MetricsTool, PlotlyTool
from aqp.agents.tools.fundamentals_tool import FundamentalsTool
from aqp.agents.tools.news_tool import NewsTool
from aqp.agents.tools.optimize_tool import OptimizeProposalTool
from aqp.agents.tools.performance_tool import PerformanceWindowTool
from aqp.agents.tools.rag_tool import HierarchyBrowseTool, RagQueryTool
from aqp.agents.tools.rating_tool import RatingTool
from aqp.agents.tools.regulatory_tool import RegulatoryLookupTool
from aqp.agents.tools.risk_tool import KillSwitchTool, LedgerTool, RiskCheckTool
from aqp.agents.tools.sentiment_tool import SentimentScoreTool
from aqp.agents.tools.technical_tool import TechnicalTool


TOOL_REGISTRY: dict[str, type] = {
    # Existing tools (kept for backwards compat with current crews)
    "duckdb_query": DuckDBQueryTool,
    "describe_bars": DescribeBarsTool,
    "chroma_search": ChromaSearchTool,
    "memory_recall": MemoryRecallTool,
    "directory_read": DirectoryReadTool,
    "backtest": BacktestTool,
    "backtrader_quick": BacktraderTool,
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
    # Phase 4 additions
    "rag_query": RagQueryTool,
    "hierarchy_browse": HierarchyBrowseTool,
    "regulatory_lookup": RegulatoryLookupTool,
    "annotation": AnnotationTool,
    "performance_window": PerformanceWindowTool,
    "optimize_proposal": OptimizeProposalTool,
    "sentiment_score": SentimentScoreTool,
}


def get_tool(name: str):
    """Look up a tool class by name (used by the crew YAML loader)."""
    if name not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {name}. Known: {sorted(TOOL_REGISTRY)}")
    return TOOL_REGISTRY[name]()


__all__ = [
    "AnnotationTool",
    "BacktestTool",
    "BacktraderTool",
    "ChromaSearchTool",
    "DescribeBarsTool",
    "DirectoryReadTool",
    "DuckDBQueryTool",
    "FundamentalsTool",
    "HierarchyBrowseTool",
    "KillSwitchTool",
    "LedgerTool",
    "MemoryRecallTool",
    "MetricsTool",
    "NewsTool",
    "OptimizeProposalTool",
    "PerformanceWindowTool",
    "PlotlyTool",
    "RagQueryTool",
    "RatingTool",
    "RegulatoryLookupTool",
    "RiskCheckTool",
    "SentimentScoreTool",
    "TechnicalTool",
    "WalkForwardTool",
    "get_tool",
]
