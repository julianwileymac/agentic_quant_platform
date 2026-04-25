"""Analyst estimates, price targets, forward EPS/EBITDA/PE/Sales estimates."""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal

from pydantic import Field, field_validator

from aqp.providers.base import Data, QueryParams


def _upper(v: str | None) -> str | None:
    return v.upper() if isinstance(v, str) else v


class AnalystEstimatesQueryParams(QueryParams):
    symbol: str
    period: str = Field(default="annual")
    limit: int | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class AnalystEstimatesData(Data):
    symbol: str
    period_ending: dateType | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    revenue_avg: Decimal | None = None
    revenue_low: Decimal | None = None
    revenue_high: Decimal | None = None
    ebitda_avg: Decimal | None = None
    ebitda_low: Decimal | None = None
    ebitda_high: Decimal | None = None
    ebit_avg: Decimal | None = None
    net_income_avg: Decimal | None = None
    sga_expense_avg: Decimal | None = None
    eps_avg: Decimal | None = None
    eps_low: Decimal | None = None
    eps_high: Decimal | None = None
    analyst_count: int | None = None


class PriceTargetQueryParams(QueryParams):
    symbol: str
    limit: int | None = 50

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class PriceTargetData(Data):
    symbol: str
    analyst_firm: str | None = None
    analyst_name: str | None = None
    target_price: Decimal | None = None
    previous_target: Decimal | None = None
    action: str | None = None  # raised | lowered | reiterated | initiated
    published_ts: datetime | None = None
    news_url: str | None = None
    news_title: str | None = None


class PriceTargetConsensusQueryParams(QueryParams):
    symbol: str


class PriceTargetConsensusData(Data):
    symbol: str
    target_high: Decimal | None = None
    target_low: Decimal | None = None
    target_median: Decimal | None = None
    target_consensus: Decimal | None = None
    number_of_analysts: int | None = None


class _ForwardEstimateQP(QueryParams):
    symbol: str
    fiscal_period: str | None = None  # FY1 | FY2 | FY3 | Q1 | Q2 | ...
    calendar_year: int | None = None

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def _u(cls, v: str) -> str:
        return _upper(v) or v


class ForwardEpsEstimatesQueryParams(_ForwardEstimateQP):
    pass


class ForwardEpsEstimatesData(Data):
    symbol: str
    fiscal_period: str | None = None
    calendar_year: int | None = None
    estimated_eps_avg: Decimal | None = None
    estimated_eps_high: Decimal | None = None
    estimated_eps_low: Decimal | None = None
    number_of_analysts: int | None = None


class ForwardEbitdaEstimatesQueryParams(_ForwardEstimateQP):
    pass


class ForwardEbitdaEstimatesData(Data):
    symbol: str
    fiscal_period: str | None = None
    calendar_year: int | None = None
    estimated_ebitda_avg: Decimal | None = None
    estimated_ebitda_high: Decimal | None = None
    estimated_ebitda_low: Decimal | None = None


class ForwardPeEstimatesQueryParams(_ForwardEstimateQP):
    pass


class ForwardPeEstimatesData(Data):
    symbol: str
    fiscal_period: str | None = None
    calendar_year: int | None = None
    forward_pe: Decimal | None = None


class ForwardSalesEstimatesQueryParams(_ForwardEstimateQP):
    pass


class ForwardSalesEstimatesData(Data):
    symbol: str
    fiscal_period: str | None = None
    calendar_year: int | None = None
    estimated_sales_avg: Decimal | None = None
    estimated_sales_high: Decimal | None = None
    estimated_sales_low: Decimal | None = None
