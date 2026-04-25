"""Macro / economic time-series Pydantic models.

Canonical shapes for the macro domain — treasury rates, yield curves,
federal funds rate, CPI, unemployment, NFP, GDP, money measures, Fed/BLS/
ECB rates, SOFR/SONIA, CoT, FRED series, house price index, retail prices,
balance of payments.

Each specific series inherits from :class:`EconomicObservation` so downstream
consumers can treat them uniformly while still having access to
metric-specific fields (e.g. NFP has ``private_payrolls``, yield curve has
maturity / yield pairs).
"""
from __future__ import annotations

from datetime import date as dateType, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EconomicSeries(BaseModel):
    """Metadata for an economic / macro series (FRED, BLS, ECB, …)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    series_id: str
    title: str
    source: str | None = None
    country: str | None = None
    country_iso: str | None = None
    frequency: str | None = None
    frequency_short: str | None = None
    units: str | None = None
    units_short: str | None = None
    seasonal_adjustment: str | None = None
    category: str | None = None
    release: str | None = None
    notes: str | None = None
    popularity: int | None = None
    observation_start: dateType | None = None
    observation_end: dateType | None = None
    last_updated: datetime | None = None


class EconomicObservation(BaseModel):
    """Single observation of an economic series."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    series_id: str | None = None
    country: str | None = None
    date: dateType
    value: Decimal | None = None
    prior: Decimal | None = None
    revised: Decimal | None = None
    vintage_date: dateType | None = None
    release_ts: datetime | None = None
    unit: str | None = None
    source: str | None = None
    provider: str | None = None


# ---------------------------------------------------------------------------
# Rate families
# ---------------------------------------------------------------------------


class TreasuryRate(EconomicObservation):
    tenor: str | None = None  # 1m | 3m | 6m | 1y | 2y | 5y | 10y | 30y
    nominal_rate: Decimal | None = None
    real_rate: Decimal | None = None
    is_constant_maturity: bool | None = None


class TreasuryAuction(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    cusip: str | None = None
    security_type: str | None = None
    auction_date: dateType | None = None
    issue_date: dateType | None = None
    maturity_date: dateType | None = None
    high_yield: Decimal | None = None
    bid_to_cover_ratio: Decimal | None = None
    total_accepted: Decimal | None = None
    total_tendered: Decimal | None = None


class TreasuryPrice(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    cusip: str | None = None
    date: dateType
    price: Decimal | None = None
    yield_to_maturity: Decimal | None = None
    coupon: Decimal | None = None
    maturity_date: dateType | None = None


class YieldCurve(BaseModel):
    """Snapshot of a yield curve."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    date: dateType
    country: str | None = None
    curve_name: str | None = None
    points: list[dict[str, Any]] = Field(default_factory=list)  # [{maturity, rate}, ...]


class FederalFundsRate(EconomicObservation):
    upper_bound: Decimal | None = None
    lower_bound: Decimal | None = None
    target_type: str | None = None  # target | target_range


class Sofr(EconomicObservation):
    volume: Decimal | None = None
    percentile_1: Decimal | None = None
    percentile_25: Decimal | None = None
    percentile_75: Decimal | None = None
    percentile_99: Decimal | None = None


class SoniaRate(EconomicObservation):
    volume: Decimal | None = None
    trimmed_mean: Decimal | None = None


class EcbInterestRate(EconomicObservation):
    rate_type: str | None = None  # main_refinancing | deposit | marginal_lending


# ---------------------------------------------------------------------------
# Price / inflation
# ---------------------------------------------------------------------------


class ConsumerPriceIndex(EconomicObservation):
    region: str | None = None
    category: str | None = None  # all_items | food | energy | core
    index_value: Decimal | None = None
    yoy_change: Decimal | None = None
    mom_change: Decimal | None = None


class ConsumerConfidence(EconomicObservation):
    index_value: Decimal | None = None
    expectations: Decimal | None = None
    present_situation: Decimal | None = None


class HousePriceIndex(EconomicObservation):
    region: str | None = None
    hpi_type: str | None = None  # purchase | refinance | all_transactions
    index_value: Decimal | None = None
    yoy_change: Decimal | None = None


class RetailPrices(EconomicObservation):
    product: str | None = None
    region: str | None = None
    price: Decimal | None = None


# ---------------------------------------------------------------------------
# Activity / employment
# ---------------------------------------------------------------------------


class Unemployment(EconomicObservation):
    rate: Decimal | None = None
    labor_force: Decimal | None = None
    employed: Decimal | None = None
    u6_rate: Decimal | None = None


class NonFarmPayrolls(EconomicObservation):
    change: Decimal | None = None
    private_payrolls: Decimal | None = None
    government_payrolls: Decimal | None = None
    unemployment_rate: Decimal | None = None
    average_hourly_earnings: Decimal | None = None


class GdpNominal(EconomicObservation):
    gdp_usd: Decimal | None = None
    yoy_change: Decimal | None = None


class GdpReal(EconomicObservation):
    gdp_usd: Decimal | None = None
    yoy_change: Decimal | None = None
    qoq_change: Decimal | None = None


class GdpForecast(EconomicObservation):
    forecast_value: Decimal | None = None
    forecast_horizon: str | None = None  # next_q | next_year | 2y | 5y
    forecaster: str | None = None


# ---------------------------------------------------------------------------
# Monetary aggregates / BoP
# ---------------------------------------------------------------------------


class MoneyMeasures(EconomicObservation):
    m0: Decimal | None = None
    m1: Decimal | None = None
    m2: Decimal | None = None
    m3: Decimal | None = None


class BalanceOfPayments(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    country: str
    period: dateType
    current_account: Decimal | None = None
    capital_account: Decimal | None = None
    financial_account: Decimal | None = None
    net_errors_and_omissions: Decimal | None = None
    change_in_reserves: Decimal | None = None
    trade_balance: Decimal | None = None


# ---------------------------------------------------------------------------
# Futures / positioning
# ---------------------------------------------------------------------------


class CotReport(BaseModel):
    """CFTC Commitment of Traders row."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    report_type: str | None = None  # legacy | disaggregated | financial | tff
    commodity: str
    commodity_code: str | None = None
    market: str | None = None
    exchange: str | None = None
    report_date: dateType
    open_interest: Decimal | None = None
    noncommercial_long: Decimal | None = None
    noncommercial_short: Decimal | None = None
    noncommercial_spreading: Decimal | None = None
    commercial_long: Decimal | None = None
    commercial_short: Decimal | None = None
    nonreportable_long: Decimal | None = None
    nonreportable_short: Decimal | None = None
    trader_count: int | None = None
    concentration_4_long: Decimal | None = None
    concentration_4_short: Decimal | None = None
    source: str = "CFTC"


class BlsSeries(BaseModel):
    """BLS series metadata (wrapped the way OpenBB standard_models do)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    series_id: str
    survey: str | None = None
    measure_data_type: str | None = None
    seasonal_adjustment: str | None = None
    title: str | None = None
    units: str | None = None


class FredSeriesMeta(BaseModel):
    """FRED series master (mirrors the existing ``fred_series`` SQL table)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    series_id: str
    title: str
    frequency: str | None = None
    frequency_short: str | None = None
    units: str | None = None
    seasonal_adjustment: str | None = None
    observation_start: dateType | None = None
    observation_end: dateType | None = None
    last_updated: datetime | None = None
    release_id: int | None = None
    category_id: int | None = None
    popularity: int | None = None
    notes: str | None = None


class FredObservation(EconomicObservation):
    """Typed FRED observation; exactly an :class:`EconomicObservation`."""
