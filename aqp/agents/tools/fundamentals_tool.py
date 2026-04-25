"""Fundamentals snapshot tool.

Uses the shared provider policy resolver (Alpha Vantage primary when
configured, yfinance fallback) and emits a compact, yfinance-shaped
snapshot for existing analyst prompts.
"""
from __future__ import annotations

import logging
from datetime import datetime

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FundamentalsInput(BaseModel):
    vt_symbol: str = Field(..., description="Canonical vt_symbol (e.g. AAPL.NASDAQ)")
    as_of: str | None = Field(
        default=None,
        description="ISO date string; only metadata that isn't time-travel sensitive is returned",
    )


_FIELD_MAP = {
    "symbol": "ticker",
    "shortName": "name",
    "sector": "sector",
    "industry": "industry",
    "country": "country",
    "currency": "currency",
    "marketCap": "market_cap",
    "enterpriseValue": "enterprise_value",
    "trailingPE": "trailing_pe",
    "forwardPE": "forward_pe",
    "priceToSalesTrailing12Months": "price_to_sales",
    "priceToBook": "price_to_book",
    "pegRatio": "peg_ratio",
    "trailingEps": "trailing_eps",
    "forwardEps": "forward_eps",
    "earningsGrowth": "earnings_growth",
    "revenueGrowth": "revenue_growth",
    "profitMargins": "profit_margin",
    "operatingMargins": "operating_margin",
    "grossMargins": "gross_margin",
    "returnOnAssets": "return_on_assets",
    "returnOnEquity": "return_on_equity",
    "debtToEquity": "debt_to_equity",
    "quickRatio": "quick_ratio",
    "currentRatio": "current_ratio",
    "freeCashflow": "free_cashflow",
    "operatingCashflow": "operating_cashflow",
    "dividendYield": "dividend_yield",
    "payoutRatio": "payout_ratio",
    "beta": "beta",
    "fiftyTwoWeekHigh": "fifty_two_week_high",
    "fiftyTwoWeekLow": "fifty_two_week_low",
    "fiftyDayAverage": "fifty_day_average",
    "twoHundredDayAverage": "two_hundred_day_average",
    "averageVolume": "average_volume",
}


def _ticker_root(vt_symbol: str) -> str:
    """Return the plain ticker (strip ``.EXCHANGE`` suffix)."""
    return vt_symbol.split(".", 1)[0]


def compute_fundamentals_snapshot(
    vt_symbol: str,
    as_of: datetime | str | None = None,
) -> dict[str, object]:
    """Fetch a fundamentals snapshot via the shared provider resolver.

    Returns an empty dict when providers are unreachable or the ticker is
    unknown — the analyst prompt is expected to handle sparse data.
    """
    try:
        from aqp.data.fundamentals import resolve_fundamentals_one

        payload = resolve_fundamentals_one(_ticker_root(vt_symbol))
    except Exception as exc:
        logger.warning("fundamentals resolver failed for %s: %s", vt_symbol, exc)
        return {}

    snapshot: dict[str, object] = {}
    for out_key, in_key in _FIELD_MAP.items():
        value = payload.get(in_key)
        if value is not None:
            snapshot[out_key] = value
    if not snapshot:
        return {}

    # Derived helpers commonly referenced by the analyst prompt.
    if snapshot.get("fiftyDayAverage") and snapshot.get("twoHundredDayAverage"):
        try:
            snapshot["_sma50_over_sma200"] = float(snapshot["fiftyDayAverage"]) / float(
                snapshot["twoHundredDayAverage"]
            )
        except (TypeError, ZeroDivisionError):  # pragma: no cover
            pass
    snapshot["_as_of_hint"] = (
        as_of if isinstance(as_of, str) else (as_of.isoformat() if as_of else "")
    )
    return snapshot


def _format_snapshot(snapshot: dict[str, object]) -> str:
    if not snapshot:
        return "fundamentals: unavailable"
    lines = [f"{k},{v}" for k, v in snapshot.items()]
    return "key,value\n" + "\n".join(lines)


class FundamentalsTool(BaseTool):
    name: str = "fundamentals_snapshot"
    description: str = (
        "Fetch a compact fundamentals sheet (trailing/forward PE, margins, "
        "growth, leverage, dividend) for a ticker via yfinance. Returns a "
        "CSV-style 'key,value' table."
    )
    args_schema: type[BaseModel] = FundamentalsInput

    def _run(self, vt_symbol: str, as_of: str | None = None) -> str:  # type: ignore[override]
        snapshot = compute_fundamentals_snapshot(vt_symbol, as_of)
        return _format_snapshot(snapshot)
