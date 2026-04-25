"""Tests for fundamentals Pydantic models."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from aqp.core.domain.fundamentals import (
    BalanceSheet,
    CashFlowStatement,
    EarningsCallTranscript,
    FinancialRatios,
    FinancialStatement,
    HistoricalDividend,
    HistoricalMarketCap,
    HistoricalSplit,
    IncomeStatement,
    KeyMetrics,
    ManagementDiscussionAnalysis,
    PeriodType,
    RevenueBusinessLine,
    RevenueGeographic,
)


def test_balance_sheet_basic():
    bs = BalanceSheet(
        symbol="AAPL",
        period=date(2025, 12, 31),
        period_type=PeriodType.ANNUAL,
        total_assets=Decimal("500_000_000"),
        total_liabilities=Decimal("200_000_000"),
        total_equity=Decimal("300_000_000"),
        cash_and_equivalents=Decimal("60_000_000"),
    )
    assert bs.symbol == "AAPL"
    assert bs.total_assets == 500_000_000
    assert bs.period_type is PeriodType.ANNUAL


def test_income_statement_basic():
    inc = IncomeStatement(
        symbol="AAPL",
        period=date(2025, 12, 31),
        revenue=Decimal("400_000_000"),
        gross_profit=Decimal("200_000_000"),
        net_income=Decimal("100_000_000"),
        eps=Decimal("6.25"),
        weighted_average_shares_outstanding=Decimal("16_000_000"),
    )
    assert inc.eps == Decimal("6.25")
    assert inc.revenue == 400_000_000


def test_cash_flow_statement_basic():
    cf = CashFlowStatement(
        symbol="AAPL",
        period=date(2025, 12, 31),
        net_cash_provided_by_operating_activities=Decimal("120_000_000"),
        free_cash_flow=Decimal("90_000_000"),
        capital_expenditure=Decimal("-30_000_000"),
    )
    assert cf.free_cash_flow == 90_000_000


def test_financial_ratios_basic():
    r = FinancialRatios(
        symbol="AAPL",
        period=date(2025, 12, 31),
        current_ratio=Decimal("1.5"),
        return_on_equity=Decimal("0.35"),
        debt_equity_ratio=Decimal("1.2"),
    )
    assert r.current_ratio == Decimal("1.5")


def test_key_metrics_basic():
    km = KeyMetrics(
        symbol="AAPL",
        period=date(2025, 12, 31),
        market_cap=Decimal("3_000_000_000_000"),
        enterprise_value=Decimal("2_900_000_000_000"),
        pe_ratio=Decimal("32"),
        pb_ratio=Decimal("45"),
    )
    assert km.pe_ratio == 32


def test_earnings_call_transcript_content():
    t = EarningsCallTranscript(
        symbol="AAPL",
        period=date(2025, 12, 31),
        fiscal_year=2025,
        fiscal_period="Q4",
        call_ts=datetime(2026, 1, 25, 17, 0),
        content="Tim Cook: Today we're pleased to report record Q4 results...",
    )
    assert "record Q4" in t.content


def test_management_discussion_analysis():
    m = ManagementDiscussionAnalysis(
        symbol="AAPL",
        period=date(2025, 12, 31),
        content="In fiscal 2025, we continued to invest in our Services business...",
        word_count=12000,
    )
    assert m.word_count == 12000


def test_historical_dividend():
    d = HistoricalDividend(
        symbol="AAPL",
        date=date(2025, 11, 14),
        dividend=Decimal("0.25"),
        currency="USD",
    )
    assert d.dividend == Decimal("0.25")


def test_historical_split():
    s = HistoricalSplit(
        symbol="AAPL",
        date=date(2020, 8, 31),
        numerator=Decimal("4"),
        denominator=Decimal("1"),
        ratio="4:1",
    )
    assert s.ratio == "4:1"


def test_historical_market_cap():
    hmc = HistoricalMarketCap(
        symbol="AAPL",
        date=date(2026, 4, 1),
        market_cap=Decimal("3_200_000_000_000"),
    )
    assert hmc.market_cap > 0


def test_revenue_business_line():
    r = RevenueBusinessLine(
        symbol="AAPL",
        period=date(2025, 12, 31),
        business_line="iPhone",
        revenue=Decimal("250_000_000_000"),
        percent_of_total=Decimal("0.52"),
    )
    assert r.business_line == "iPhone"


def test_revenue_geographic():
    r = RevenueGeographic(
        symbol="AAPL",
        period=date(2025, 12, 31),
        region="Americas",
        revenue=Decimal("170_000_000_000"),
    )
    assert r.region == "Americas"


def test_financial_statement_polymorphic():
    fs = FinancialStatement(
        symbol="AAPL",
        period=date(2025, 12, 31),
        statement_type="balance_sheet",
        rows={"total_assets": 500_000_000, "total_equity": 300_000_000},
    )
    assert fs.statement_type == "balance_sheet"
    assert fs.rows["total_assets"] == 500_000_000


def test_fundamentals_extra_fields_allowed():
    # ``extra='allow'`` should let provider-specific columns survive round-trip.
    bs = BalanceSheet(
        symbol="AAPL",
        period=date(2025, 12, 31),
        provider_specific_field="extra_data",
    )
    # Accessible via model_dump()
    dumped = bs.model_dump()
    assert dumped.get("provider_specific_field") == "extra_data"
