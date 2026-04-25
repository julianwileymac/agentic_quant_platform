"""Shared fundamentals resolver (Alpha Vantage primary with fallback)."""
from __future__ import annotations

import logging
from typing import Any

from aqp.config import settings
from aqp.data.sources.alpha_vantage.client import (
    AlphaVantageClient,
    AlphaVantageClientError,
)

logger = logging.getLogger(__name__)


class FundamentalsProviderError(RuntimeError):
    """Raised when no fundamentals provider could satisfy the request."""


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw in {"None", "null", "N/A", "-"}:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _alpha_vantage_configured() -> bool:
    return bool(str(settings.alpha_vantage_api_key or "").strip())


def _fetch_alpha_vantage_fundamentals(ticker: str) -> dict[str, Any]:
    client = AlphaVantageClient()
    overview = client.overview(ticker)
    if not overview:
        raise ValueError(f"no fundamentals payload for {ticker!r}")

    quote: dict[str, Any] = {}
    try:
        quote_payload = client.global_quote(ticker)
        quote = dict(quote_payload.get("Global Quote") or {})
    except AlphaVantageClientError:
        quote = {}

    gross_margin = _as_float(overview.get("GrossProfitTTM"))
    revenue_ttm = _as_float(overview.get("RevenueTTM"))
    if gross_margin is not None and revenue_ttm not in (None, 0):
        gross_margin = gross_margin / revenue_ttm
    else:
        gross_margin = _as_float(overview.get("GrossMargin"))

    payload = {
        "ticker": str(overview.get("Symbol") or ticker).upper(),
        "name": overview.get("Name"),
        "sector": overview.get("Sector"),
        "industry": overview.get("Industry"),
        "country": overview.get("Country"),
        "currency": overview.get("Currency"),
        "exchange": overview.get("Exchange"),
        "website": overview.get("OfficialSite"),
        "summary": overview.get("Description"),
        "market_cap": _as_float(overview.get("MarketCapitalization")),
        "enterprise_value": _as_float(overview.get("EnterpriseValue")),
        "trailing_pe": _as_float(overview.get("TrailingPE")) or _as_float(overview.get("PERatio")),
        "forward_pe": _as_float(overview.get("ForwardPE")),
        "price_to_book": _as_float(overview.get("PriceToBookRatio")),
        "price_to_sales": _as_float(overview.get("PriceToSalesRatioTTM")),
        "peg_ratio": _as_float(overview.get("PEGRatio")),
        "trailing_eps": _as_float(overview.get("EPS")),
        "forward_eps": _as_float(overview.get("ForwardEPS")),
        "dividend_yield": _as_float(overview.get("DividendYield")),
        "dividend_rate": _as_float(overview.get("DividendPerShare")),
        "payout_ratio": _as_float(overview.get("PayoutRatio")),
        "shares_outstanding": _as_float(overview.get("SharesOutstanding")),
        "float_shares": _as_float(overview.get("SharesFloat")),
        "beta": _as_float(overview.get("Beta")),
        "profit_margin": _as_float(overview.get("ProfitMargin")),
        "operating_margin": _as_float(overview.get("OperatingMarginTTM")),
        "gross_margin": gross_margin,
        "revenue_growth": _as_float(overview.get("QuarterlyRevenueGrowthYOY")),
        "earnings_growth": _as_float(overview.get("QuarterlyEarningsGrowthYOY")),
        "return_on_equity": _as_float(overview.get("ReturnOnEquityTTM")),
        "return_on_assets": _as_float(overview.get("ReturnOnAssetsTTM")),
        "debt_to_equity": _as_float(overview.get("DebtToEquity")),
        "quick_ratio": _as_float(overview.get("QuickRatio")),
        "current_ratio": _as_float(overview.get("CurrentRatio")),
        "free_cashflow": _as_float(overview.get("FreeCashFlowTTM")),
        "operating_cashflow": _as_float(overview.get("OperatingCashflowTTM"))
        or _as_float(overview.get("OperatingCashFlowTTM")),
        "fifty_two_week_high": _as_float(overview.get("52WeekHigh")),
        "fifty_two_week_low": _as_float(overview.get("52WeekLow")),
        "fifty_day_average": _as_float(overview.get("50DayMovingAverage")),
        "two_hundred_day_average": _as_float(overview.get("200DayMovingAverage")),
        "average_volume": _as_float(overview.get("AverageVolume")),
        "last_price": _as_float(quote.get("05. price")),
        "previous_close": _as_float(quote.get("08. previous close")),
        "day_high": _as_float(quote.get("03. high")),
        "day_low": _as_float(quote.get("04. low")),
    }
    populated = [v for k, v in payload.items() if k != "ticker" and v not in (None, "", [])]
    if not populated:
        raise ValueError(f"no fundamentals payload for {ticker!r}")
    return payload


def _fetch_yfinance_fundamentals(ticker: str) -> dict[str, Any]:
    from aqp.data.ingestion import YahooFinanceSource

    return YahooFinanceSource().fetch_fundamentals_one(ticker)


def resolve_fundamentals_one(
    ticker: str,
    *,
    provider: str | None = None,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    policy = str(provider or settings.fundamentals_provider or "auto").strip().lower()
    if policy not in {"auto", "alpha_vantage", "yfinance"}:
        policy = "auto"

    if policy == "yfinance":
        return _fetch_yfinance_fundamentals(ticker)

    if policy == "alpha_vantage":
        if not _alpha_vantage_configured():
            if allow_fallback:
                return _fetch_yfinance_fundamentals(ticker)
            raise FundamentalsProviderError("AQP_ALPHA_VANTAGE_API_KEY is not configured")
        try:
            return _fetch_alpha_vantage_fundamentals(ticker)
        except Exception as exc:
            if allow_fallback:
                logger.info("alpha_vantage fundamentals failed for %s, falling back to yfinance: %s", ticker, exc)
                return _fetch_yfinance_fundamentals(ticker)
            raise

    # auto
    if _alpha_vantage_configured():
        try:
            return _fetch_alpha_vantage_fundamentals(ticker)
        except Exception as exc:
            logger.info("alpha_vantage fundamentals failed for %s, falling back to yfinance: %s", ticker, exc)
    return _fetch_yfinance_fundamentals(ticker)
