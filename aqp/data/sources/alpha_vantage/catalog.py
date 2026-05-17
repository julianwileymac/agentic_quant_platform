"""Alpha Vantage endpoint metadata used by API routes and UI controls."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aqp.data.sources.alpha_vantage._cache import default_ttl

_ICEBERG_NAMESPACE = "aqp_alpha_vantage"


@dataclass(frozen=True)
class AlphaVantagePartitionField:
    """A single Iceberg partition field expressed in a wrapper-agnostic shape."""

    source_column: str
    transform: str  # identity | bucket[N] | month | year | day | hour
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_column": self.source_column,
            "transform": self.transform,
            "name": self.name or f"{self.source_column}_{self.transform}",
        }


@dataclass(frozen=True)
class AlphaVantageParameter:
    name: str
    required: bool = False
    type: str = "string"
    default: Any | None = None
    options: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "type": self.type,
            "default": self.default,
            "options": list(self.options),
            "description": self.description,
        }


@dataclass(frozen=True)
class AlphaVantageFunction:
    id: str
    label: str
    category: str
    route: str
    function: str
    domain: str
    output_shape: str
    parameters: list[AlphaVantageParameter] = field(default_factory=list)
    cache_ttl_seconds: float = 0.0
    lake_supported: bool = False
    iceberg_table: str | None = None
    partition_spec: tuple[AlphaVantagePartitionField, ...] = field(default_factory=tuple)
    timestamp_column: str | None = None
    symbol_column: str | None = None

    @property
    def iceberg_identifier(self) -> str | None:
        if not self.iceberg_table:
            return None
        return f"{_ICEBERG_NAMESPACE}.{self.iceberg_table}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "route": self.route,
            "function": self.function,
            "domain": self.domain,
            "output_shape": self.output_shape,
            "parameters": [param.to_dict() for param in self.parameters],
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "lake_supported": self.lake_supported,
            "iceberg_table": self.iceberg_table,
            "iceberg_identifier": self.iceberg_identifier,
            "partition_spec": [field.to_dict() for field in self.partition_spec],
            "timestamp_column": self.timestamp_column,
            "symbol_column": self.symbol_column,
        }


_SYMBOL = AlphaVantageParameter("symbol", required=True, description="Ticker symbol, e.g. IBM")
_OUTPUTSIZE = AlphaVantageParameter(
    "outputsize",
    type="select",
    default="compact",
    options=["compact", "full"],
    description="compact returns the latest points; full returns the full supported window.",
)
_DATATYPE = AlphaVantageParameter(
    "datatype",
    type="select",
    default="json",
    options=["json", "csv"],
    description="Response format requested from Alpha Vantage.",
)
_ENTITLEMENT = AlphaVantageParameter(
    "entitlement",
    type="select",
    options=["realtime", "delayed"],
    description="Premium freshness control where the endpoint supports it.",
)


_PARTITION_SYMBOL_MONTH = (
    AlphaVantagePartitionField(source_column="vt_symbol", transform="bucket[16]", name="vt_symbol_bucket"),
    AlphaVantagePartitionField(source_column="timestamp", transform="month", name="timestamp_month"),
)
_PARTITION_SYMBOL = (
    AlphaVantagePartitionField(source_column="vt_symbol", transform="identity", name="vt_symbol"),
)
_PARTITION_MONTH = (
    AlphaVantagePartitionField(source_column="as_of", transform="month", name="as_of_month"),
)


FUNCTIONS: list[AlphaVantageFunction] = [
    AlphaVantageFunction(
        id="timeseries.intraday",
        label="Intraday OHLCV",
        category="timeseries",
        route="/alpha-vantage/timeseries/intraday",
        function="TIME_SERIES_INTRADAY",
        domain="market.bars",
        output_shape="bars",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TIME_SERIES_INTRADAY", {}),
        iceberg_table="time_series_intraday",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[
            _SYMBOL,
            AlphaVantageParameter(
                "interval",
                required=True,
                type="select",
                default="5min",
                options=["1min", "5min", "15min", "30min", "60min"],
            ),
            _OUTPUTSIZE,
            AlphaVantageParameter("month", description="Historical month in YYYY-MM format."),
            AlphaVantageParameter("adjusted", type="boolean", default=True),
            AlphaVantageParameter("extended_hours", type="boolean", default=True),
            _DATATYPE,
            _ENTITLEMENT,
        ],
    ),
    AlphaVantageFunction(
        id="timeseries.daily_adjusted",
        label="Daily Adjusted OHLCV",
        category="timeseries",
        route="/alpha-vantage/timeseries/daily_adjusted",
        function="TIME_SERIES_DAILY_ADJUSTED",
        domain="market.bars",
        output_shape="bars",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TIME_SERIES_DAILY_ADJUSTED", {}),
        iceberg_table="time_series_daily_adjusted",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[_SYMBOL, _OUTPUTSIZE, _DATATYPE],
    ),
    AlphaVantageFunction(
        id="timeseries.daily",
        label="Daily OHLCV",
        category="timeseries",
        route="/alpha-vantage/timeseries/daily",
        function="TIME_SERIES_DAILY",
        domain="market.bars",
        output_shape="bars",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TIME_SERIES_DAILY", {}),
        iceberg_table="time_series_daily",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[_SYMBOL, _OUTPUTSIZE, _DATATYPE],
    ),
    AlphaVantageFunction(
        id="timeseries.weekly_adjusted",
        label="Weekly Adjusted OHLCV",
        category="timeseries",
        route="/alpha-vantage/timeseries/weekly_adjusted",
        function="TIME_SERIES_WEEKLY_ADJUSTED",
        domain="market.bars",
        output_shape="bars",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TIME_SERIES_WEEKLY_ADJUSTED", {}),
        iceberg_table="time_series_weekly_adjusted",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[_SYMBOL, _DATATYPE],
    ),
    AlphaVantageFunction(
        id="timeseries.monthly_adjusted",
        label="Monthly Adjusted OHLCV",
        category="timeseries",
        route="/alpha-vantage/timeseries/monthly_adjusted",
        function="TIME_SERIES_MONTHLY_ADJUSTED",
        domain="market.bars",
        output_shape="bars",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TIME_SERIES_MONTHLY_ADJUSTED", {}),
        iceberg_table="time_series_monthly_adjusted",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[_SYMBOL, _DATATYPE],
    ),
    AlphaVantageFunction(
        id="fundamentals.listing",
        label="Listing Status",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/listing",
        function="LISTING_STATUS",
        domain="security.master",
        output_shape="csv",
        cache_ttl_seconds=default_ttl("LISTING_STATUS", {}),
        iceberg_table="listing_status",
        partition_spec=_PARTITION_MONTH,
        timestamp_column="as_of",
        symbol_column="vt_symbol",
        parameters=[
            AlphaVantageParameter("state", type="select", default="active", options=["active", "delisted"]),
            AlphaVantageParameter("date", description="Listing date snapshot in YYYY-MM-DD format."),
            _DATATYPE,
        ],
    ),
    AlphaVantageFunction(
        id="fundamentals.overview",
        label="Company Overview",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/overview",
        function="OVERVIEW",
        domain="fundamentals.overview",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("OVERVIEW", {}),
        iceberg_table="fundamentals_overview",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.income_statement",
        label="Income Statement",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/income",
        function="INCOME_STATEMENT",
        domain="fundamentals.statements",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("INCOME_STATEMENT", {}),
        iceberg_table="fundamentals_income_statement",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.balance_sheet",
        label="Balance Sheet",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/balance",
        function="BALANCE_SHEET",
        domain="fundamentals.statements",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("BALANCE_SHEET", {}),
        iceberg_table="fundamentals_balance_sheet",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.cash_flow",
        label="Cash Flow",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/cashflow",
        function="CASH_FLOW",
        domain="fundamentals.statements",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("CASH_FLOW", {}),
        iceberg_table="fundamentals_cash_flow",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.earnings",
        label="Earnings History",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/earnings",
        function="EARNINGS",
        domain="fundamentals.earnings",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("EARNINGS", {}),
        iceberg_table="fundamentals_earnings",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.dividends",
        label="Dividends",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/dividends",
        function="DIVIDENDS",
        domain="fundamentals.corporate_actions",
        output_shape="series",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("DIVIDENDS", {}),
        iceberg_table="fundamentals_dividends",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="fundamentals.splits",
        label="Splits",
        category="fundamentals",
        route="/alpha-vantage/fundamentals/splits",
        function="SPLITS",
        domain="fundamentals.corporate_actions",
        output_shape="series",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("SPLITS", {}),
        iceberg_table="fundamentals_splits",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="intelligence.news",
        label="News and Sentiment",
        category="intelligence",
        route="/alpha-vantage/intelligence/news",
        function="NEWS_SENTIMENT",
        domain="news.sentiment",
        output_shape="feed",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("NEWS_SENTIMENT", {}),
        iceberg_table="intelligence_news_sentiment",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[
            AlphaVantageParameter("tickers", description="Comma-separated tickers."),
            AlphaVantageParameter("topics", description="Comma-separated AlphaVantage topics."),
            AlphaVantageParameter("time_from", description="YYYYMMDDTHHMM lower bound."),
            AlphaVantageParameter("time_to", description="YYYYMMDDTHHMM upper bound."),
            AlphaVantageParameter("sort", type="select", options=["LATEST", "EARLIEST", "RELEVANCE"]),
            AlphaVantageParameter("limit", type="number", default=50),
        ],
    ),
    AlphaVantageFunction(
        id="intelligence.top_movers",
        label="Top Gainers and Losers",
        category="intelligence",
        route="/alpha-vantage/intelligence/top-movers",
        function="TOP_GAINERS_LOSERS",
        domain="market.movers",
        output_shape="object",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("TOP_GAINERS_LOSERS", {}),
        iceberg_table="intelligence_top_movers",
        partition_spec=_PARTITION_MONTH,
        timestamp_column="as_of",
        symbol_column="vt_symbol",
        parameters=[],
    ),
    AlphaVantageFunction(
        id="intelligence.insider",
        label="Insider Transactions",
        category="intelligence",
        route="/alpha-vantage/intelligence/insider",
        function="INSIDER_TRANSACTIONS",
        domain="intelligence.insider",
        output_shape="series",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("INSIDER_TRANSACTIONS", {}),
        iceberg_table="intelligence_insider",
        partition_spec=_PARTITION_SYMBOL,
        symbol_column="vt_symbol",
        parameters=[_SYMBOL],
    ),
    AlphaVantageFunction(
        id="technicals.sma",
        label="Simple Moving Average",
        category="technicals",
        route="/alpha-vantage/technicals/SMA",
        function="SMA",
        domain="market.indicators",
        output_shape="series",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("SMA", {}),
        iceberg_table="technicals_sma",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[
            _SYMBOL,
            AlphaVantageParameter(
                "interval",
                required=True,
                type="select",
                default="daily",
                options=["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
            ),
            AlphaVantageParameter("time_period", type="number", default=20),
            AlphaVantageParameter("series_type", type="select", default="close", options=["open", "high", "low", "close"]),
            AlphaVantageParameter("month", description="Intraday historical month in YYYY-MM format."),
            _ENTITLEMENT,
        ],
    ),
    AlphaVantageFunction(
        id="technicals.rsi",
        label="Relative Strength Index",
        category="technicals",
        route="/alpha-vantage/technicals/RSI",
        function="RSI",
        domain="market.indicators",
        output_shape="series",
        lake_supported=True,
        cache_ttl_seconds=default_ttl("RSI", {}),
        iceberg_table="technicals_rsi",
        partition_spec=_PARTITION_SYMBOL_MONTH,
        timestamp_column="timestamp",
        symbol_column="vt_symbol",
        parameters=[
            _SYMBOL,
            AlphaVantageParameter(
                "interval",
                required=True,
                type="select",
                default="daily",
                options=["1min", "5min", "15min", "30min", "60min", "daily", "weekly", "monthly"],
            ),
            AlphaVantageParameter("time_period", type="number", default=14),
            AlphaVantageParameter("series_type", type="select", default="close", options=["open", "high", "low", "close"]),
        ],
    ),
]


def list_functions() -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in FUNCTIONS]


def function_by_id(function_id: str) -> dict[str, Any] | None:
    wanted = str(function_id or "").strip().lower()
    for entry in FUNCTIONS:
        if entry.id.lower() == wanted or entry.function.lower() == wanted:
            return entry.to_dict()
    return None


def get_function(function_id: str) -> AlphaVantageFunction | None:
    """Return the typed :class:`AlphaVantageFunction` for ``function_id``."""
    wanted = str(function_id or "").strip().lower()
    for entry in FUNCTIONS:
        if entry.id.lower() == wanted or entry.function.lower() == wanted:
            return entry
    return None


def lake_supported_functions() -> list[AlphaVantageFunction]:
    return [entry for entry in FUNCTIONS if entry.lake_supported]


def iceberg_namespace() -> str:
    return _ICEBERG_NAMESPACE


__all__ = [
    "AlphaVantageFunction",
    "AlphaVantageParameter",
    "AlphaVantagePartitionField",
    "FUNCTIONS",
    "function_by_id",
    "get_function",
    "iceberg_namespace",
    "lake_supported_functions",
    "list_functions",
]
