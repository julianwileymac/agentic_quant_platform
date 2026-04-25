"""Fundamentals persistence tables.

- ``financial_statements`` — polymorphic (balance_sheet/income_statement/cash_flow)
  statement rows. The JSON ``rows`` column carries the full line-item blob;
  headline fields are promoted to dedicated columns so strategy code can
  filter by common ratios without parsing JSON.
- ``financial_ratios`` — computed/provider ratios per period.
- ``key_metrics`` — snapshot metrics (pe, market_cap, EV, yields…).
- ``historical_market_cap`` — timeseries of market cap / enterprise value.
- ``revenue_breakdowns`` — business-line + geographic revenue.
- ``earnings_call_transcripts`` + ``management_discussion_analyses`` — narrative
  content with full-text index-friendly shape.
- ``reported_financials`` — as-reported (non-standardised) rows.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)

from aqp.persistence.models import Base, _uuid


class FinancialStatement(Base):
    """One reported statement for an issuer / period / type.

    ``statement_type`` = ``balance_sheet`` | ``income_statement`` |
    ``cash_flow``. The unique index on ``(issuer_id, period, period_type,
    statement_type)`` enforces one row per (issuer, period, type).
    """

    __tablename__ = "financial_statements"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    statement_type = Column(String(32), nullable=False, index=True)
    period = Column(Date, nullable=False, index=True)
    period_type = Column(String(16), nullable=False, default="annual")
    fiscal_year = Column(Integer, nullable=True)
    fiscal_period = Column(String(8), nullable=True)
    currency = Column(String(16), default="USD")
    reporting_currency = Column(String(16), nullable=True)

    # Selected headline fields for quick filtering (others live in ``rows``).
    revenue = Column(Float, nullable=True)
    gross_profit = Column(Float, nullable=True)
    operating_income = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    ebitda = Column(Float, nullable=True)
    total_assets = Column(Float, nullable=True)
    total_liabilities = Column(Float, nullable=True)
    total_equity = Column(Float, nullable=True)
    cash_and_equivalents = Column(Float, nullable=True)
    operating_cash_flow = Column(Float, nullable=True)
    free_cash_flow = Column(Float, nullable=True)
    capital_expenditure = Column(Float, nullable=True)

    rows = Column(JSON, default=dict)  # Full line-item blob.
    as_of = Column(DateTime, nullable=True)
    source = Column(String(64), nullable=True)
    source_filing_accession = Column(String(32), nullable=True, index=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_fin_stmt",
            "issuer_id",
            "period",
            "period_type",
            "statement_type",
            unique=True,
        ),
        Index("ix_fin_stmt_symbol_period", "symbol", "period"),
    )


class FinancialRatios(Base):
    __tablename__ = "financial_ratios"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    period = Column(Date, nullable=False, index=True)
    period_type = Column(String(16), nullable=False, default="annual")
    fiscal_year = Column(Integer, nullable=True)

    current_ratio = Column(Float, nullable=True)
    quick_ratio = Column(Float, nullable=True)
    cash_ratio = Column(Float, nullable=True)
    gross_profit_margin = Column(Float, nullable=True)
    operating_profit_margin = Column(Float, nullable=True)
    net_profit_margin = Column(Float, nullable=True)
    return_on_assets = Column(Float, nullable=True)
    return_on_equity = Column(Float, nullable=True)
    return_on_invested_capital = Column(Float, nullable=True)
    debt_ratio = Column(Float, nullable=True)
    debt_equity_ratio = Column(Float, nullable=True)
    interest_coverage = Column(Float, nullable=True)
    asset_turnover = Column(Float, nullable=True)
    inventory_turnover = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    payout_ratio = Column(Float, nullable=True)

    extra = Column(JSON, default=dict)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_fin_ratios", "issuer_id", "period", "period_type", unique=True),
    )


class KeyMetrics(Base):
    __tablename__ = "key_metrics"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    period = Column(Date, nullable=False, index=True)
    period_type = Column(String(16), nullable=False, default="annual")
    fiscal_year = Column(Integer, nullable=True)

    market_cap = Column(Float, nullable=True)
    enterprise_value = Column(Float, nullable=True)
    pe_ratio = Column(Float, nullable=True)
    pb_ratio = Column(Float, nullable=True)
    price_to_sales = Column(Float, nullable=True)
    ev_to_ebitda = Column(Float, nullable=True)
    ev_to_free_cash_flow = Column(Float, nullable=True)
    earnings_yield = Column(Float, nullable=True)
    free_cash_flow_yield = Column(Float, nullable=True)
    revenue_per_share = Column(Float, nullable=True)
    book_value_per_share = Column(Float, nullable=True)
    free_cash_flow_per_share = Column(Float, nullable=True)
    debt_to_equity = Column(Float, nullable=True)
    net_debt_to_ebitda = Column(Float, nullable=True)
    working_capital = Column(Float, nullable=True)

    extra = Column(JSON, default=dict)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("uq_key_metrics", "issuer_id", "period", "period_type", unique=True),
    )


class HistoricalMarketCap(Base):
    __tablename__ = "historical_market_cap"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    date = Column(Date, nullable=False, index=True)
    market_cap = Column(Float, nullable=False)
    enterprise_value = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (Index("uq_hist_mcap", "issuer_id", "date", unique=True),)


class RevenueBreakdown(Base):
    """Combined business-line / geographic revenue breakdown row."""

    __tablename__ = "revenue_breakdowns"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    period = Column(Date, nullable=False, index=True)
    fiscal_year = Column(Integer, nullable=True)
    breakdown_type = Column(String(16), nullable=False, index=True)  # business | geographic
    segment = Column(String(240), nullable=False)
    region = Column(String(120), nullable=True)
    country = Column(String(64), nullable=True)
    revenue = Column(Float, nullable=True)
    percent_of_total = Column(Float, nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_rev_breakdown_issuer_period", "issuer_id", "period", "breakdown_type"),
    )


class EarningsCallTranscript(Base):
    __tablename__ = "earnings_call_transcripts"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    fiscal_year = Column(Integer, nullable=True)
    fiscal_quarter = Column(String(8), nullable=True)
    call_ts = Column(DateTime, nullable=True, index=True)
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)
    participants = Column(JSON, default=list)
    url = Column(String(1024), nullable=True)
    sentiment = Column(JSON, default=dict)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "uq_earnings_transcript",
            "issuer_id",
            "fiscal_year",
            "fiscal_quarter",
            unique=True,
        ),
    )


class ManagementDiscussionAnalysis(Base):
    __tablename__ = "management_discussion_analyses"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    fiscal_year = Column(Integer, nullable=True)
    period = Column(Date, nullable=True, index=True)
    period_type = Column(String(16), nullable=False, default="annual")
    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=True)
    source_filing_accession = Column(String(32), nullable=True, index=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ReportedFinancials(Base):
    """As-reported (non-standardised) financial rows."""

    __tablename__ = "reported_financials"
    id = Column(String(36), primary_key=True, default=_uuid)
    issuer_id = Column(String(36), ForeignKey("issuers.id"), nullable=True, index=True)
    symbol = Column(String(64), nullable=True, index=True)
    period = Column(Date, nullable=False)
    period_type = Column(String(16), nullable=False, default="annual")
    template = Column(String(120), nullable=True)
    rows = Column(JSON, default=dict)
    source_filing_accession = Column(String(32), nullable=True)
    provider = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
