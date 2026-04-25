"""FinRobot-style section agents that produce one section of an equity report.

Each subclass of :class:`BaseSectionAgent` owns a tight LLM prompt,
takes the same shared inputs (price summary, fundamentals snapshot,
peer set, news digest), and returns a :class:`FinancialReport`. The
:class:`EquityReportPipeline` in :mod:`aqp.agents.financial.equity_pipeline`
orchestrates them.

Section agents are registered under ``kind="equity_section"`` so the
Research UI can dynamically list them and let users opt sections in /
out.
"""

from aqp.agents.financial.equity_sections.section_base import BaseSectionAgent
from aqp.agents.financial.equity_sections.tagline import TaglineAgent
from aqp.agents.financial.equity_sections.company_overview import CompanyOverviewAgent
from aqp.agents.financial.equity_sections.investment_overview import (
    InvestmentOverviewAgent,
)
from aqp.agents.financial.equity_sections.valuation_overview import (
    ValuationOverviewAgent,
)
from aqp.agents.financial.equity_sections.risks import RisksAgent
from aqp.agents.financial.equity_sections.competitor_analysis import (
    CompetitorAnalysisAgent,
)
from aqp.agents.financial.equity_sections.major_takeaways import MajorTakeawaysAgent
from aqp.agents.financial.equity_sections.news_summary import NewsSummaryAgent

__all__ = [
    "BaseSectionAgent",
    "CompanyOverviewAgent",
    "CompetitorAnalysisAgent",
    "InvestmentOverviewAgent",
    "MajorTakeawaysAgent",
    "NewsSummaryAgent",
    "RisksAgent",
    "TaglineAgent",
    "ValuationOverviewAgent",
]
