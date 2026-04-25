"""Fundamentals Pydantic models.

These mirror OpenBB's ``balance_sheet``/``income_statement``/``cash_flow``/
``financial_ratios``/``key_metrics`` standard_models but are centralised here
so every provider (FMP, AlphaVantage, Intrinio, SEC EDGAR, yfinance) can flow
into the same canonical schema. The Fetcher pattern in
:mod:`aqp.providers` wraps these classes so ingestion round-trips through
this single shape.

``extra="allow"`` is used throughout so provider-specific columns survive a
round-trip without having to predeclare every long-tail field.
"""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PeriodType(StrEnum):
    """Reporting-period cadence."""

    ANNUAL = "annual"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    MONTHLY = "monthly"
    TTM = "ttm"
    FISCAL_YTD = "fiscal_ytd"
    INTERIM = "interim"


class _FundamentalsBase(BaseModel):
    """Shared configuration and audit fields for every fundamentals model."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    symbol: str | None = Field(default=None, description="Primary instrument ticker.")
    issuer_id: str | None = Field(default=None, description="AQP issuer foreign key.")
    period: dateType = Field(description="Period end date.")
    period_type: PeriodType = Field(default=PeriodType.ANNUAL)
    fiscal_year: int | None = None
    fiscal_period: str | None = None  # Q1/Q2/Q3/Q4/FY
    currency: str = "USD"
    reporting_currency: str | None = None
    as_of: datetime | None = None
    source: str | None = None
    source_filing_accession: str | None = None
    provider: str | None = None


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


class FinancialStatement(_FundamentalsBase):
    """Discriminated union parent for the three canonical statements."""

    statement_type: str = Field(description="balance_sheet | income_statement | cash_flow")
    rows: dict[str, Decimal | None] = Field(default_factory=dict)


class BalanceSheet(_FundamentalsBase):
    """Balance sheet line items (OpenBB-parity superset)."""

    cash_and_equivalents: Decimal | None = None
    short_term_investments: Decimal | None = None
    cash_and_short_term_investments: Decimal | None = None
    accounts_receivable: Decimal | None = None
    inventories: Decimal | None = None
    prepaid_expenses: Decimal | None = None
    other_current_assets: Decimal | None = None
    total_current_assets: Decimal | None = None

    property_plant_equipment_net: Decimal | None = None
    goodwill: Decimal | None = None
    intangible_assets: Decimal | None = None
    long_term_investments: Decimal | None = None
    tax_assets: Decimal | None = None
    other_non_current_assets: Decimal | None = None
    total_non_current_assets: Decimal | None = None
    total_assets: Decimal | None = None

    accounts_payable: Decimal | None = None
    short_term_debt: Decimal | None = None
    deferred_revenue: Decimal | None = None
    other_current_liabilities: Decimal | None = None
    total_current_liabilities: Decimal | None = None

    long_term_debt: Decimal | None = None
    deferred_revenue_non_current: Decimal | None = None
    deferred_tax_liabilities_non_current: Decimal | None = None
    other_non_current_liabilities: Decimal | None = None
    total_non_current_liabilities: Decimal | None = None
    total_liabilities: Decimal | None = None

    common_stock: Decimal | None = None
    retained_earnings: Decimal | None = None
    accumulated_other_comprehensive_income: Decimal | None = None
    other_total_stockholders_equity: Decimal | None = None
    total_stockholders_equity: Decimal | None = None
    minority_interest: Decimal | None = None
    total_equity: Decimal | None = None
    total_liabilities_and_equity: Decimal | None = None

    total_debt: Decimal | None = None
    net_debt: Decimal | None = None


class IncomeStatement(_FundamentalsBase):
    """Income statement line items."""

    revenue: Decimal | None = None
    cost_of_revenue: Decimal | None = None
    gross_profit: Decimal | None = None
    research_and_development_expenses: Decimal | None = None
    general_and_administrative_expenses: Decimal | None = None
    selling_and_marketing_expenses: Decimal | None = None
    selling_general_and_administrative_expenses: Decimal | None = None
    other_expenses: Decimal | None = None
    operating_expenses: Decimal | None = None
    depreciation_and_amortization: Decimal | None = None
    ebitda: Decimal | None = None
    operating_income: Decimal | None = None
    total_other_income_expense_net: Decimal | None = None
    income_before_tax: Decimal | None = None
    income_tax_expense: Decimal | None = None
    net_income: Decimal | None = None
    net_income_from_continuing_operations: Decimal | None = None
    net_income_from_discontinued_operations: Decimal | None = None
    eps: Decimal | None = None
    eps_diluted: Decimal | None = None
    weighted_average_shares_outstanding: Decimal | None = None
    weighted_average_shares_outstanding_diluted: Decimal | None = None


class CashFlowStatement(_FundamentalsBase):
    """Cash flow statement line items."""

    net_income: Decimal | None = None
    depreciation_and_amortization: Decimal | None = None
    deferred_income_tax: Decimal | None = None
    stock_based_compensation: Decimal | None = None
    change_in_working_capital: Decimal | None = None
    accounts_receivable_change: Decimal | None = None
    inventory_change: Decimal | None = None
    accounts_payable_change: Decimal | None = None
    other_working_capital: Decimal | None = None
    other_non_cash_items: Decimal | None = None
    net_cash_provided_by_operating_activities: Decimal | None = None

    investments_in_property_plant_and_equipment: Decimal | None = None
    acquisitions_net: Decimal | None = None
    purchases_of_investments: Decimal | None = None
    sales_maturities_of_investments: Decimal | None = None
    other_investing_activities: Decimal | None = None
    net_cash_used_for_investing_activities: Decimal | None = None

    debt_repayment: Decimal | None = None
    common_stock_issued: Decimal | None = None
    common_stock_repurchased: Decimal | None = None
    dividends_paid: Decimal | None = None
    other_financing_activities: Decimal | None = None
    net_cash_used_by_financing_activities: Decimal | None = None

    effect_of_forex_changes_on_cash: Decimal | None = None
    net_change_in_cash: Decimal | None = None
    cash_at_beginning_of_period: Decimal | None = None
    cash_at_end_of_period: Decimal | None = None
    free_cash_flow: Decimal | None = None
    capital_expenditure: Decimal | None = None


# ---------------------------------------------------------------------------
# Ratios / metrics
# ---------------------------------------------------------------------------


class FinancialRatios(_FundamentalsBase):
    """Computed or provider-reported ratios."""

    current_ratio: Decimal | None = None
    quick_ratio: Decimal | None = None
    cash_ratio: Decimal | None = None
    days_of_sales_outstanding: Decimal | None = None
    days_of_inventory_outstanding: Decimal | None = None
    operating_cycle: Decimal | None = None
    days_of_payables_outstanding: Decimal | None = None
    cash_conversion_cycle: Decimal | None = None

    gross_profit_margin: Decimal | None = None
    operating_profit_margin: Decimal | None = None
    pretax_profit_margin: Decimal | None = None
    net_profit_margin: Decimal | None = None
    effective_tax_rate: Decimal | None = None

    return_on_assets: Decimal | None = None
    return_on_equity: Decimal | None = None
    return_on_capital_employed: Decimal | None = None
    return_on_invested_capital: Decimal | None = None

    debt_ratio: Decimal | None = None
    debt_equity_ratio: Decimal | None = None
    long_term_debt_to_capitalization: Decimal | None = None
    total_debt_to_capitalization: Decimal | None = None
    interest_coverage: Decimal | None = None
    cash_flow_to_debt_ratio: Decimal | None = None

    fixed_asset_turnover: Decimal | None = None
    asset_turnover: Decimal | None = None
    inventory_turnover: Decimal | None = None
    receivables_turnover: Decimal | None = None
    payables_turnover: Decimal | None = None

    operating_cash_flow_per_share: Decimal | None = None
    free_cash_flow_per_share: Decimal | None = None
    cash_per_share: Decimal | None = None
    payout_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None
    dividend_payout_ratio: Decimal | None = None


class KeyMetrics(_FundamentalsBase):
    """Snapshot valuation + capital-markets metrics."""

    revenue_per_share: Decimal | None = None
    net_income_per_share: Decimal | None = None
    operating_cash_flow_per_share: Decimal | None = None
    free_cash_flow_per_share: Decimal | None = None
    book_value_per_share: Decimal | None = None
    tangible_book_value_per_share: Decimal | None = None
    shareholders_equity_per_share: Decimal | None = None
    interest_debt_per_share: Decimal | None = None

    market_cap: Decimal | None = None
    enterprise_value: Decimal | None = None
    pe_ratio: Decimal | None = None
    price_to_sales: Decimal | None = None
    pocf_ratio: Decimal | None = None
    pfcf_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    ptb_ratio: Decimal | None = None
    ev_to_sales: Decimal | None = None
    enterprise_value_over_ebitda: Decimal | None = None
    ev_to_operating_cash_flow: Decimal | None = None
    ev_to_free_cash_flow: Decimal | None = None
    earnings_yield: Decimal | None = None
    free_cash_flow_yield: Decimal | None = None
    debt_to_equity: Decimal | None = None
    debt_to_assets: Decimal | None = None
    net_debt_to_ebitda: Decimal | None = None
    graham_number: Decimal | None = None
    working_capital: Decimal | None = None
    tangible_asset_value: Decimal | None = None
    net_current_asset_value: Decimal | None = None
    invested_capital: Decimal | None = None
    average_receivables: Decimal | None = None
    average_payables: Decimal | None = None
    average_inventory: Decimal | None = None
    days_sales_outstanding: Decimal | None = None
    days_payables_outstanding: Decimal | None = None
    days_of_inventory_on_hand: Decimal | None = None
    receivables_turnover: Decimal | None = None
    payables_turnover: Decimal | None = None
    inventory_turnover: Decimal | None = None


# ---------------------------------------------------------------------------
# Transcripts / MD&A
# ---------------------------------------------------------------------------


class EarningsCallTranscript(_FundamentalsBase):
    """Full text of an earnings-call transcript."""

    call_ts: datetime | None = None
    content: str = ""
    fiscal_quarter: str | None = None
    participants: list[dict[str, Any]] | None = None
    url: str | None = None


class ManagementDiscussionAnalysis(_FundamentalsBase):
    """Extracted MD&A prose."""

    content: str = ""
    word_count: int | None = None


class ReportedFinancials(_FundamentalsBase):
    """As-reported (non-standardised) filing rows."""

    template: str | None = None
    rows: dict[str, Decimal | None] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Historicals
# ---------------------------------------------------------------------------


class HistoricalDividend(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    symbol: str | None = None
    date: dateType | None = None
    dividend: Decimal | None = None
    adjusted_dividend: Decimal | None = None
    declaration_date: dateType | None = None
    record_date: dateType | None = None
    payment_date: dateType | None = None
    currency: str = "USD"


class HistoricalSplit(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    symbol: str | None = None
    date: dateType | None = None
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    ratio: str | None = None


class HistoricalMarketCap(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    symbol: str | None = None
    date: dateType | None = None
    market_cap: Decimal | None = None
    enterprise_value: Decimal | None = None


class RevenueBusinessLine(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    symbol: str | None = None
    period: dateType | None = None
    fiscal_year: int | None = None
    business_line: str | None = None
    revenue: Decimal | None = None
    percent_of_total: Decimal | None = None


class RevenueGeographic(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    symbol: str | None = None
    period: dateType | None = None
    fiscal_year: int | None = None
    region: str | None = None
    country: str | None = None
    revenue: Decimal | None = None
    percent_of_total: Decimal | None = None
