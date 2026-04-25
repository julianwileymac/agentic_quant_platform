"""Equity reference / pricing / search standard models.

Ports:

- ``equity_info`` — :class:`EquityInfoQueryParams` / :class:`EquityInfoData`
- ``equity_historical`` — OHLCV bars
- ``equity_quote`` — live quote snapshot
- ``equity_nbbo`` — L1 bid/ask with venue
- ``equity_search`` — fuzzy search by name/ticker
- ``equity_screener`` — multi-filter screener
- ``equity_peers`` — peer group lookup
- ``equity_performance`` — recent returns
- ``equity_ftd`` — fails-to-deliver report
- ``historical_market_cap``
- ``historical_eps`` / ``historical_dividends`` / ``historical_splits``
"""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------


class EquityInfoQueryParams(QueryParams):
    symbol: str = Field(description="Equity ticker.")

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityInfoData(Data):
    symbol: str = Field(description="Equity ticker.")
    name: str | None = Field(default=None, description="Common name of the company.")
    cik: str | None = None
    cusip: str | None = None
    isin: str | None = None
    lei: str | None = None
    legal_name: str | None = None
    stock_exchange: str | None = None
    sic: int | None = None
    short_description: str | None = None
    long_description: str | None = None
    ceo: str | None = None
    company_url: str | None = None
    business_address: str | None = None
    mailing_address: str | None = None
    hq_address1: str | None = None
    hq_address2: str | None = None
    hq_address_city: str | None = None
    hq_address_postal_code: str | None = None
    hq_state: str | None = None
    hq_country: str | None = None
    inc_state: str | None = None
    inc_country: str | None = None
    employees: int | None = None
    entity_legal_form: str | None = None
    entity_status: str | None = None
    latest_filing_date: dateType | None = None
    irs_number: str | None = None
    sector: str | None = None
    industry_category: str | None = None
    industry_group: str | None = None
    template: str | None = None
    standardized_active: bool | None = None
    first_fundamental_date: dateType | None = None
    last_fundamental_date: dateType | None = None
    first_stock_price_date: dateType | None = None
    last_stock_price_date: dateType | None = None


# ---------------------------------------------------------------------------
# Historical / quote / NBBO
# ---------------------------------------------------------------------------


class EquityHistoricalQueryParams(QueryParams):
    symbol: str = Field(description="Equity ticker.")
    start_date: dateType | None = None
    end_date: dateType | None = None
    interval: str | None = Field(default="1d", description="Bar interval (1d/1h/1m/…).")

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityHistoricalData(Data):
    date: dateType | datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | int | None = None
    vwap: float | None = None
    adj_close: float | None = None


class EquityQuoteQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityQuoteData(Data):
    symbol: str
    asset_type: str | None = None
    name: str | None = None
    exchange: str | None = None
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    last_price: float | None = None
    last_size: float | None = None
    last_timestamp: datetime | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    market_cap: float | None = None


class EquityNbboQueryParams(QueryParams):
    symbol: str
    date: dateType | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityNbboData(Data):
    timestamp: datetime
    symbol: str
    bid_price: float | None = None
    ask_price: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    bid_exchange: str | None = None
    ask_exchange: str | None = None
    sequence_number: int | None = None


# ---------------------------------------------------------------------------
# Search / screener / peers / performance
# ---------------------------------------------------------------------------


class EquitySearchQueryParams(QueryParams):
    query: str = Field(description="Search query (ticker or name fragment).")
    is_symbol: bool = False
    active_only: bool = True


class EquitySearchData(Data):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    asset_type: str | None = None
    market_category: str | None = None


class EquityScreenerQueryParams(QueryParams):
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    exchange: str | None = None
    market_cap_min: Decimal | None = None
    market_cap_max: Decimal | None = None
    pe_min: Decimal | None = None
    pe_max: Decimal | None = None
    dividend_yield_min: Decimal | None = None
    beta_min: Decimal | None = None
    beta_max: Decimal | None = None
    limit: int = 100


class EquityScreenerData(Data):
    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    country: str | None = None
    market_cap: Decimal | None = None
    price: Decimal | None = None
    pe_ratio: Decimal | None = None
    forward_pe: Decimal | None = None
    dividend_yield: Decimal | None = None
    beta: Decimal | None = None
    volume: Decimal | None = None


class EquityPeersQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityPeersData(Data):
    symbol: str
    peer_symbols: list[str] = Field(default_factory=list)
    selection_method: str | None = None


class EquityPerformanceQueryParams(QueryParams):
    symbol: str

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class EquityPerformanceData(Data):
    symbol: str
    one_day: Decimal | None = None
    one_week: Decimal | None = None
    one_month: Decimal | None = None
    three_month: Decimal | None = None
    six_month: Decimal | None = None
    ytd: Decimal | None = None
    one_year: Decimal | None = None
    three_year: Decimal | None = None
    five_year: Decimal | None = None
    max: Decimal | None = None


# ---------------------------------------------------------------------------
# Historicals (dividends / splits / eps / market cap / FTDs)
# ---------------------------------------------------------------------------


class HistoricalDividendsQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class HistoricalDividendsData(Data):
    symbol: str
    ex_date: dateType | None = None
    record_date: dateType | None = None
    pay_date: dateType | None = None
    declaration_date: dateType | None = None
    dividend: Decimal | None = None
    adjusted_dividend: Decimal | None = None
    currency: str = "USD"


class HistoricalSplitsQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class HistoricalSplitsData(Data):
    symbol: str
    date: dateType
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    ratio: str | None = None


class HistoricalEpsQueryParams(QueryParams):
    symbol: str
    period: str | None = "quarterly"


class HistoricalEpsData(Data):
    symbol: str
    date: dateType
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    revenue_estimate: Decimal | None = None
    revenue_actual: Decimal | None = None
    period_ending: dateType | None = None


class HistoricalMarketCapQueryParams(QueryParams):
    symbol: str
    start_date: dateType | None = None
    end_date: dateType | None = None


class HistoricalMarketCapData(Data):
    symbol: str
    date: dateType
    market_cap: Decimal
    enterprise_value: Decimal | None = None


class EquityFtdQueryParams(QueryParams):
    symbol: str | None = None
    start_date: dateType | None = None
    end_date: dateType | None = None


class EquityFtdData(Data):
    symbol: str | None = None
    cusip: str | None = None
    settlement_date: dateType
    quantity: Decimal | None = None
    description: str | None = None
