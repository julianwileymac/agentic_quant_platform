"""Common Alpha Vantage request enum values."""
from __future__ import annotations

from enum import StrEnum


class Interval(StrEnum):
    ONE_MIN = "1min"
    FIVE_MIN = "5min"
    FIFTEEN_MIN = "15min"
    THIRTY_MIN = "30min"
    SIXTY_MIN = "60min"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class OutputSize(StrEnum):
    COMPACT = "compact"
    FULL = "full"


class SeriesType(StrEnum):
    CLOSE = "close"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"


class OutputFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


class Entitlement(StrEnum):
    REALTIME = "realtime"
    DELAYED = "delayed"


class NewsSort(StrEnum):
    LATEST = "LATEST"
    EARLIEST = "EARLIEST"
    RELEVANCE = "RELEVANCE"


class MaType(StrEnum):
    SMA = "0"
    EMA = "1"
    WMA = "2"
    DEMA = "3"
    TEMA = "4"
    TRIMA = "5"
    KAMA = "6"
    MAMA = "7"
    T3 = "8"


class AnalyticsCalculation(StrEnum):
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    CUMULATIVE_RETURN = "CUMULATIVE_RETURN"
    VARIANCE = "VARIANCE"
    STDDEV = "STDDEV"
    MAX = "MAX"
    MIN = "MIN"


__all__ = [
    "AnalyticsCalculation",
    "Entitlement",
    "Interval",
    "MaType",
    "NewsSort",
    "OutputFormat",
    "OutputSize",
    "SeriesType",
]
