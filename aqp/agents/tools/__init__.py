"""CrewAI tool adapters — the platform's public agent-facing API.

The production path uses ``crewai.tools.BaseTool``. Python 3.14 dev
environments cannot currently install CrewAI (published wheels cap at
``<3.14``), so we install a tiny import-time compatibility shim when the
real package is unavailable. The shim implements only what AQP's tools
need: subclassing, class attributes, construction, and direct ``_run``
execution through :class:`aqp.agents.runtime.AgentRuntime`.
"""

from __future__ import annotations

import sys
import types


try:  # pragma: no cover - exercised when CrewAI is installed.
    from crewai.tools import BaseTool as _CrewAIBaseTool  # noqa: F401
except ImportError:  # pragma: no cover - cold Python 3.14 dev install.
    crewai_pkg = sys.modules.setdefault("crewai", types.ModuleType("crewai"))
    tools_mod = types.ModuleType("crewai.tools")

    class BaseTool:  # type: ignore[no-redef]
        name: str = ""
        description: str = ""
        args_schema = None

        def __init__(self, **_: object) -> None:
            return None

        def _run(self, *args: object, **kwargs: object) -> str:
            raise NotImplementedError

    tools_mod.BaseTool = BaseTool
    crewai_pkg.tools = tools_mod  # type: ignore[attr-defined]
    sys.modules["crewai.tools"] = tools_mod

from aqp.agents.tools.analytics_tools import (
    ChartPatternTool,
    CointegrationTool,
    FactorScreenTool,
    HftMetricsTool,
    MultiIndicatorVoteTool,
    OptionGreeksTool,
    OptionSpreadTool,
    RealisedVolTool,
    RegimeClassifierTool,
)
from aqp.agents.tools.annotation_tool import AnnotationTool
from aqp.agents.tools.backtest_tool import BacktestTool, WalkForwardTool
from aqp.agents.tools.backtrader_tool import BacktraderTool
from aqp.agents.tools.chroma_tool import ChromaSearchTool, MemoryRecallTool
from aqp.agents.tools.directory_tool import DirectoryReadTool
from aqp.agents.tools.duckdb_tool import DescribeBarsTool, DuckDBQueryTool
from aqp.agents.tools.evaluator_tool import MetricsTool, PlotlyTool
from aqp.agents.tools.fundamentals_tool import FundamentalsTool
from aqp.agents.tools.margin_tool import PortfolioMarginTool
from aqp.agents.tools.news_tool import NewsTool
from aqp.agents.tools.optimize_tool import OptimizeProposalTool
from aqp.agents.tools.performance_tool import PerformanceWindowTool
from aqp.agents.tools.rag_tool import HierarchyBrowseTool, RagQueryTool
from aqp.agents.tools.rating_tool import RatingTool
from aqp.agents.tools.regulatory_tool import RegulatoryLookupTool
from aqp.agents.tools.risk_tool import KillSwitchTool, LedgerTool, RiskCheckTool
from aqp.agents.tools.sentiment_tool import SentimentScoreTool
from aqp.agents.tools.simulation_tool import InsightImpactTool
from aqp.agents.tools.technical_tool import TechnicalTool
from aqp.agents.tools.volatility_tool import HistoricalVolatilityTool


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
    # Phase 4 (refactor): MCP-compliant tools for the Research Debate graph.
    "historical_volatility": HistoricalVolatilityTool,
    "portfolio_margin": PortfolioMarginTool,
    "insight_impact": InsightImpactTool,
    # Inspiration rehydration tools (Phase 7).
    "cointegration_tool": CointegrationTool,
    "regime_classifier_tool": RegimeClassifierTool,
    "realised_vol_tool": RealisedVolTool,
    "factor_screen_tool": FactorScreenTool,
    "hft_metrics_tool": HftMetricsTool,
    "multi_indicator_vote_tool": MultiIndicatorVoteTool,
    "chart_pattern_tool": ChartPatternTool,
    "option_greeks_tool": OptionGreeksTool,
    "option_spread_tool": OptionSpreadTool,
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
    "ChartPatternTool",
    "ChromaSearchTool",
    "CointegrationTool",
    "DescribeBarsTool",
    "DirectoryReadTool",
    "DuckDBQueryTool",
    "FactorScreenTool",
    "FundamentalsTool",
    "HftMetricsTool",
    "HierarchyBrowseTool",
    "HistoricalVolatilityTool",
    "InsightImpactTool",
    "KillSwitchTool",
    "LedgerTool",
    "MemoryRecallTool",
    "MetricsTool",
    "MultiIndicatorVoteTool",
    "NewsTool",
    "OptimizeProposalTool",
    "OptionGreeksTool",
    "OptionSpreadTool",
    "PerformanceWindowTool",
    "PlotlyTool",
    "PortfolioMarginTool",
    "RagQueryTool",
    "RatingTool",
    "RealisedVolTool",
    "RegimeClassifierTool",
    "RegulatoryLookupTool",
    "RiskCheckTool",
    "SentimentScoreTool",
    "TechnicalTool",
    "WalkForwardTool",
    "get_tool",
]
