"""FinRobot-style multi-agent role packs.

Five "mini-crews" each wired to a narrow research task:

- :class:`MarketForecaster` — multi-horizon point + narrative forecast.
- :class:`DocumentAnalyzer` — SEC filings / transcripts Q&A (summarise,
  extract, cite).
- :class:`FinancialReportBuilder` — render a structured equity-research
  report from analyst outputs.
- :class:`TradeStrategist` — synthesise an execution plan + risk bracket
  from a decision.
- :class:`EquityResearch` — umbrella crew that chains the above four
  into a single deliverable.

Every crew returns a ``dict`` with a ``"report"`` JSON payload and a
``"usage"`` block (tokens + USD cost) so MLflow logging stays uniform.
"""
from __future__ import annotations

from aqp.agents.financial.base import BaseFinancialCrew, FinancialReport
from aqp.agents.financial.document_analyzer import DocumentAnalyzer
from aqp.agents.financial.equity_research import EquityResearch
from aqp.agents.financial.financial_report import FinancialReportBuilder
from aqp.agents.financial.market_forecaster import MarketForecaster
from aqp.agents.financial.trade_strategist import TradeStrategist

# FinRobot-style section agents — registered as ``kind="equity_section"``.
import aqp.agents.financial.equity_sections  # noqa: F401

__all__ = [
    "BaseFinancialCrew",
    "DocumentAnalyzer",
    "EquityResearch",
    "FinancialReport",
    "FinancialReportBuilder",
    "MarketForecaster",
    "TradeStrategist",
]
