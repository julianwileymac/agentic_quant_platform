"""Calendar-event Pydantic models + market-session extensions.

OpenBB-parity models for earnings / dividend / split / IPO / economic
calendars plus exchange-calendar extensions (:class:`MarketHoliday`,
:class:`HalfDay`, :class:`SpecialSession`) that complement the existing
:class:`aqp.core.exchange_hours.MarketHoursDatabase`.
"""
from __future__ import annotations

from datetime import date as dateType, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _CalendarBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, arbitrary_types_allowed=True)
    symbol: str | None = None
    issuer_id: str | None = None
    source: str | None = None
    provider: str | None = None


# ---------------------------------------------------------------------------
# Corporate / earnings calendars
# ---------------------------------------------------------------------------


class CalendarEarnings(_CalendarBase):
    """Earnings-announcement calendar entry."""

    report_date: dateType | None = None
    report_ts: datetime | None = None
    fiscal_period: str | None = None
    fiscal_year: int | None = None
    eps_estimate: Decimal | None = None
    eps_actual: Decimal | None = None
    revenue_estimate: Decimal | None = None
    revenue_actual: Decimal | None = None
    time_of_day: str | None = None  # bmo | amc | dmh
    company_name: str | None = None
    surprise_pct: Decimal | None = None


class CalendarDividend(_CalendarBase):
    """Upcoming dividend calendar entry."""

    ex_date: dateType | None = None
    record_date: dateType | None = None
    pay_date: dateType | None = None
    declaration_date: dateType | None = None
    amount: Decimal | None = None
    adjusted_amount: Decimal | None = None
    currency: str = "USD"
    company_name: str | None = None
    frequency: str | None = None


class CalendarSplit(_CalendarBase):
    """Upcoming split calendar entry."""

    ex_date: dateType | None = None
    pay_date: dateType | None = None
    numerator: Decimal | None = None
    denominator: Decimal | None = None
    ratio: str | None = None
    company_name: str | None = None


class CalendarIpo(_CalendarBase):
    """Upcoming IPO calendar entry."""

    ipo_date: dateType | None = None
    exchange: str | None = None
    offer_price_low: Decimal | None = None
    offer_price_high: Decimal | None = None
    offer_price_final: Decimal | None = None
    shares_offered: Decimal | None = None
    company_name: str | None = None
    underwriters: list[str] = Field(default_factory=list)
    status: str | None = None


# ---------------------------------------------------------------------------
# Macro / economic calendar
# ---------------------------------------------------------------------------


class EconomicCalendar(BaseModel):
    """Upcoming economic-event release."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    event: str
    country: str | None = None
    country_iso: str | None = None
    release_date: dateType | None = None
    release_ts: datetime | None = None
    reference_period: str | None = None
    importance: int | None = None  # 1-3
    actual: Decimal | None = None
    consensus: Decimal | None = None
    previous: Decimal | None = None
    revised: Decimal | None = None
    unit: str | None = None
    frequency: str | None = None
    source: str | None = None


# ---------------------------------------------------------------------------
# Aggregate container
# ---------------------------------------------------------------------------


class CalendarEvents(BaseModel):
    """Aggregated calendar response (mixed event types)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    earnings: list[CalendarEarnings] = Field(default_factory=list)
    dividends: list[CalendarDividend] = Field(default_factory=list)
    splits: list[CalendarSplit] = Field(default_factory=list)
    ipos: list[CalendarIpo] = Field(default_factory=list)
    economic: list[EconomicCalendar] = Field(default_factory=list)
    window_start: dateType | None = None
    window_end: dateType | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Exchange-session extensions
# ---------------------------------------------------------------------------


class MarketHoliday(BaseModel):
    """A full-day market holiday (no trading)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    exchange: str
    date: dateType
    name: str | None = None
    is_observed: bool = True


class HalfDay(BaseModel):
    """A half-day trading session (early close)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    exchange: str
    date: dateType
    open: time | None = None
    close: time
    name: str | None = None


class SpecialSession(BaseModel):
    """Arbitrary overnight / weekend / auction / out-of-band session."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)
    exchange: str
    date: dateType
    session_name: str
    open: time
    close: time
    notes: str | None = None
