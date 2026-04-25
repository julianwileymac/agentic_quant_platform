"""Fundamentals standard models (statements + growth + ratios + metrics + transcripts).

Data classes extend the authoritative primitives in
:mod:`aqp.core.domain.fundamentals` so the OpenBB provider wire shape and
the platform's canonical schema are the *same type*.
"""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.core.domain.fundamentals import (
    BalanceSheet,
    CashFlowStatement,
    EarningsCallTranscript,
    FinancialRatios,
    HistoricalDividend,
    HistoricalMarketCap,
    HistoricalSplit,
    IncomeStatement,
    KeyMetrics,
    ManagementDiscussionAnalysis,
    ReportedFinancials,
    RevenueBusinessLine,
    RevenueGeographic,
)
from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


class _SymbolPeriodQP(QueryParams):
    """Shared ``symbol`` + ``period`` + ``limit`` pattern."""

    symbol: str
    period: str | None = Field(default="annual", description="annual | quarterly | ttm")
    limit: int | None = Field(default=5, description="Rows to return.")

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


class BalanceSheetQueryParams(_SymbolPeriodQP):
    pass


class BalanceSheetData(Data, BalanceSheet):
    """Balance-sheet rows (inherits the full :class:`BalanceSheet` shape)."""


class IncomeStatementQueryParams(_SymbolPeriodQP):
    pass


class IncomeStatementData(Data, IncomeStatement):
    pass


class CashFlowQueryParams(_SymbolPeriodQP):
    pass


class CashFlowData(Data, CashFlowStatement):
    pass


# Growth variants — same fields, but values represent YoY/QoQ deltas.


class BalanceSheetGrowthQueryParams(_SymbolPeriodQP):
    pass


class BalanceSheetGrowthData(Data, BalanceSheet):
    growth_period: str | None = None


class IncomeStatementGrowthQueryParams(_SymbolPeriodQP):
    pass


class IncomeStatementGrowthData(Data, IncomeStatement):
    growth_period: str | None = None


class CashFlowGrowthQueryParams(_SymbolPeriodQP):
    pass


class CashFlowGrowthData(Data, CashFlowStatement):
    growth_period: str | None = None


# ---------------------------------------------------------------------------
# Ratios + metrics
# ---------------------------------------------------------------------------


class FinancialRatiosQueryParams(_SymbolPeriodQP):
    pass


class FinancialRatiosData(Data, FinancialRatios):
    pass


class KeyMetricsQueryParams(_SymbolPeriodQP):
    pass


class KeyMetricsData(Data, KeyMetrics):
    pass


# ---------------------------------------------------------------------------
# Transcripts / MD&A
# ---------------------------------------------------------------------------


class EarningsCallTranscriptQueryParams(QueryParams):
    symbol: str
    fiscal_year: int | None = None
    fiscal_quarter: str | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EarningsCallTranscriptData(Data, EarningsCallTranscript):
    pass


class ManagementDiscussionAnalysisQueryParams(QueryParams):
    symbol: str
    fiscal_year: int | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class ManagementDiscussionAnalysisData(Data, ManagementDiscussionAnalysis):
    pass


# ---------------------------------------------------------------------------
# Historicals (dividends / splits / market cap / revenue breakdowns)
# ---------------------------------------------------------------------------


class HistoricalDividendsQP(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class HistoricalDividendsData(Data, HistoricalDividend):
    pass


class HistoricalSplitsQP(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class HistoricalSplitsData(Data, HistoricalSplit):
    pass


class HistoricalMarketCapQP(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class HistoricalMarketCapData(Data, HistoricalMarketCap):
    pass


class RevenueBusinessLineQueryParams(_SymbolPeriodQP):
    pass


class RevenueBusinessLineData(Data, RevenueBusinessLine):
    pass


class RevenueGeographicQueryParams(_SymbolPeriodQP):
    pass


class RevenueGeographicData(Data, RevenueGeographic):
    pass


# ---------------------------------------------------------------------------
# As-reported financials
# ---------------------------------------------------------------------------


class ReportedFinancialsQueryParams(_SymbolPeriodQP):
    template: str | None = Field(
        default=None,
        description="Provider-specific template name (e.g. intrinio template).",
    )


class ReportedFinancialsData(Data, ReportedFinancials):
    pass
