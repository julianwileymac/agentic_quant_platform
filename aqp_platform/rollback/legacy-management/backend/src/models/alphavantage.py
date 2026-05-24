"""Alpha Vantage request/response DTOs.

Most response models are re-exported from the ``alphavantage_client`` library
so the backend API surfaces exactly the same shapes that streaming producers
and Argo bulk-loaders consume. Backend-only envelopes (bulk-load request,
rate-limit health, stream toggle) are defined here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# Re-export client-library Pydantic models. These are imported lazily so that
# the backend still boots even if the client library failed to install.
try:  # pragma: no cover - optional at import time
    from alphavantage_client.models import (
        AnalyticsFixedWindow,
        AnalyticsSlidingWindow,
        AVMetadata,
        AVResponse,
        BalanceSheetReport,
        CashFlowReport,
        CommodityPoint,
        CommoditySeries,
        CompanyOverview,
        CryptoBar,
        CryptoIntradaySeries,
        CryptoQuote,
        CryptoSeries,
        Dividend,
        EarningsCalendarEntry,
        EarningsEstimate,
        EarningsReport,
        EarningsTranscript,
        EarningsTranscriptTurn,
        EconIndicatorPoint,
        EconIndicatorSeries,
        EtfProfile,
        FundamentalsEarnings,
        FxBar,
        FxIntradaySeries,
        FxRate,
        FxSeries,
        GlobalQuote,
        IncomeStatementReport,
        IndexCatalogEntry,
        IndexSeries,
        IndicatorPoint,
        IndicatorSeries,
        InsiderTransaction,
        InstitutionalHolding,
        IpoCalendarEntry,
        ListingStatusEntry,
        MarketStatusEntry,
        MarketStatusPayload,
        NewsArticle,
        NewsSentimentPayload,
        OhlcvBar,
        OptionChain,
        OptionContract,
        OptionsRatioPoint,
        ResponseStatus,
        SharesOutstandingPoint,
        Split,
        SymbolSearchMatch,
        SymbolSentiment,
        TickerSentiment,
        TimeSeriesPayload,
        TopGainersLosersPayload,
        TopMover,
    )

    CLIENT_MODELS_AVAILABLE = True
except ImportError:  # pragma: no cover
    CLIENT_MODELS_AVAILABLE = False

    class _Stub(BaseModel):
        model_config = ConfigDict(extra="allow")

    # Provide minimal stubs so imports don't crash; every attribute access
    # resolves to an empty Pydantic model.
    AnalyticsFixedWindow = AnalyticsSlidingWindow = AVMetadata = AVResponse = _Stub  # type: ignore[assignment]
    BalanceSheetReport = CashFlowReport = CommodityPoint = CommoditySeries = _Stub  # type: ignore[assignment]
    CompanyOverview = CryptoBar = CryptoIntradaySeries = CryptoQuote = CryptoSeries = _Stub  # type: ignore[assignment]
    Dividend = EarningsCalendarEntry = EarningsEstimate = EarningsReport = _Stub  # type: ignore[assignment]
    EarningsTranscript = EarningsTranscriptTurn = EconIndicatorPoint = _Stub  # type: ignore[assignment]
    EconIndicatorSeries = EtfProfile = FundamentalsEarnings = FxBar = _Stub  # type: ignore[assignment]
    FxIntradaySeries = FxRate = FxSeries = GlobalQuote = IncomeStatementReport = _Stub  # type: ignore[assignment]
    IndexCatalogEntry = IndexSeries = IndicatorPoint = IndicatorSeries = _Stub  # type: ignore[assignment]
    InsiderTransaction = InstitutionalHolding = IpoCalendarEntry = _Stub  # type: ignore[assignment]
    ListingStatusEntry = MarketStatusEntry = MarketStatusPayload = _Stub  # type: ignore[assignment]
    NewsArticle = NewsSentimentPayload = OhlcvBar = OptionChain = OptionContract = _Stub  # type: ignore[assignment]
    OptionsRatioPoint = ResponseStatus = SharesOutstandingPoint = Split = _Stub  # type: ignore[assignment]
    SymbolSearchMatch = SymbolSentiment = TickerSentiment = TimeSeriesPayload = _Stub  # type: ignore[assignment]
    TopGainersLosersPayload = TopMover = _Stub  # type: ignore[assignment]


class AlphaVantageHealth(BaseModel):
    """Response from ``GET /api/alphavantage/health``."""

    enabled: bool
    credentials_loaded: bool
    base_url: str
    rpm_limit: int
    daily_limit: int
    cache_backend: str
    client_version: Optional[str] = None
    client_available: bool = True
    message: Optional[str] = None


class AlphaVantageUsage(BaseModel):
    """Live rate-limiter snapshot."""

    rpm_limit: int
    daily_limit: int
    requests_this_minute: int
    requests_today: int
    tokens_available: float
    next_refill_seconds: float
    daily_reset_utc: str


class BulkLoadRequest(BaseModel):
    """Argo workflow trigger payload."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(
        description=(
            "One of: timeseries | fundamentals | intraday-backfill | universe | "
            "news | earnings | fx | crypto | technicals | commodities | economics"
        ),
    )
    symbols: List[str] = Field(default_factory=list)
    date_range: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional {start,end} bounds (YYYY-MM-DD or YYYY-MM).",
    )
    extra_params: Dict[str, Any] = Field(default_factory=dict)
    target_bucket: str = Field(default="av-raw")


class BulkLoadResponse(BaseModel):
    workflow_name: str
    namespace: str
    category: str
    status: str
    submitted_at: str
    symbols: List[str]
    parameters: Dict[str, Any]


class StreamToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable: bool
    replicas: int = Field(default=1, ge=0, le=10)


class StreamToggleResponse(BaseModel):
    deployment: str
    namespace: str
    desired_replicas: int
    previous_replicas: int
    ready: bool
    message: str


class SymbolLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: str


class TimeSeriesQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    function: str = Field(
        default="daily",
        description="intraday|daily|daily_adjusted|weekly|weekly_adjusted|monthly|monthly_adjusted|global_quote|bulk_quotes",
    )
    interval: Optional[str] = None
    outputsize: Optional[str] = Field(default=None, description="compact|full")
    month: Optional[str] = None
    adjusted: Optional[bool] = None
    extended_hours: Optional[bool] = None
    entitlement: Optional[str] = None


class TechnicalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indicator: str
    symbol: str
    interval: str = "daily"
    time_period: Optional[int] = 20
    series_type: Optional[str] = "close"
    month: Optional[str] = None
    extras: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "AlphaVantageHealth",
    "AlphaVantageUsage",
    "AnalyticsFixedWindow",
    "AnalyticsSlidingWindow",
    "AVMetadata",
    "AVResponse",
    "BalanceSheetReport",
    "BulkLoadRequest",
    "BulkLoadResponse",
    "CashFlowReport",
    "CLIENT_MODELS_AVAILABLE",
    "CommodityPoint",
    "CommoditySeries",
    "CompanyOverview",
    "CryptoBar",
    "CryptoIntradaySeries",
    "CryptoQuote",
    "CryptoSeries",
    "Dividend",
    "EarningsCalendarEntry",
    "EarningsEstimate",
    "EarningsReport",
    "EarningsTranscript",
    "EarningsTranscriptTurn",
    "EconIndicatorPoint",
    "EconIndicatorSeries",
    "EtfProfile",
    "FundamentalsEarnings",
    "FxBar",
    "FxIntradaySeries",
    "FxRate",
    "FxSeries",
    "GlobalQuote",
    "IncomeStatementReport",
    "IndexCatalogEntry",
    "IndexSeries",
    "IndicatorPoint",
    "IndicatorSeries",
    "InsiderTransaction",
    "InstitutionalHolding",
    "IpoCalendarEntry",
    "ListingStatusEntry",
    "MarketStatusEntry",
    "MarketStatusPayload",
    "NewsArticle",
    "NewsSentimentPayload",
    "OhlcvBar",
    "OptionChain",
    "OptionContract",
    "OptionsRatioPoint",
    "ResponseStatus",
    "SharesOutstandingPoint",
    "Split",
    "StreamToggleRequest",
    "StreamToggleResponse",
    "SymbolLookupRequest",
    "SymbolSearchMatch",
    "SymbolSentiment",
    "TechnicalQuery",
    "TickerSentiment",
    "TimeSeriesPayload",
    "TimeSeriesQuery",
    "TopGainersLosersPayload",
    "TopMover",
]
