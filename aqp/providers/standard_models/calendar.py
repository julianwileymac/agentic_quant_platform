"""Calendar standard models — earnings, dividend, split, IPO, economic."""
from __future__ import annotations

from datetime import date as dateType

from pydantic import Field

from aqp.core.domain.calendar_events import (
    CalendarDividend,
    CalendarEarnings,
    CalendarIpo,
    CalendarSplit,
    EconomicCalendar,
)
from aqp.providers.base import Data, QueryParams


class _RangeQP(QueryParams):
    start_date: dateType | None = None
    end_date: dateType | None = None


class CalendarEarningsQueryParams(_RangeQP):
    symbol: str | None = None


class CalendarEarningsData(Data, CalendarEarnings):
    pass


class CalendarDividendQueryParams(_RangeQP):
    symbol: str | None = None


class CalendarDividendData(Data, CalendarDividend):
    pass


class CalendarSplitsQueryParams(_RangeQP):
    symbol: str | None = None


class CalendarSplitsData(Data, CalendarSplit):
    pass


class CalendarIpoQueryParams(_RangeQP):
    limit: int | None = 100


class CalendarIpoData(Data, CalendarIpo):
    pass


class EconomicCalendarQueryParams(_RangeQP):
    country: str | None = None
    importance: int | None = None


class EconomicCalendarData(Data, EconomicCalendar):
    pass
