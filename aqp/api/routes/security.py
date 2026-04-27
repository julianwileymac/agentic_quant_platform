"""Per-security reference data endpoints powering the Live Market page.

Endpoints use a Redis read-through cache (see :mod:`aqp.data.cache`). The
fundamentals route is provider-aware (Alpha Vantage primary with optional
yfinance fallback), while the remaining facets remain yfinance-backed.
The UI consumes these via ``/data/security/{vt_symbol}/{facet}``.

vt_symbol can be either ``AAPL`` or ``AAPL.NASDAQ`` — the exchange suffix
is stripped before hitting yfinance since yfinance uses plain tickers.

Error contract
--------------
- 404: ticker unknown / yfinance produced no payload
- 502: yfinance call raised unexpectedly (network, upstream down)
- 503: ``yfinance`` package not importable (install ``aqp[dev]`` or
  ``pip install yfinance``)
Every error body is ``{detail: str, hint: str, code: str}`` so the UI
can render friendly messages.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from aqp.api.schemas import (
    CalendarResponse,
    CorporateActionsResponse,
    FundamentalsResponse,
    NewsItem,
    NewsResponse,
    QuoteSnapshot,
)
from aqp.data.cache import cached_json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data/security", tags=["security"])

# Cache scopes — one per facet so operators can flush granularly.
_SCOPE_FUNDAMENTALS = "security:fundamentals"
_SCOPE_NEWS = "security:news"
_SCOPE_CALENDAR = "security:calendar"
_SCOPE_CORPORATE = "security:corporate"
_SCOPE_QUOTE = "security:quote"

# TTLs (seconds).
_TTL_FUNDAMENTALS = 60 * 60        # 1h
_TTL_NEWS = 15 * 60                # 15m
_TTL_CALENDAR = 60 * 60            # 1h
_TTL_CORPORATE = 6 * 60 * 60       # 6h
_TTL_QUOTE = 5                     # 5s


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ticker_from_vt(vt_symbol: str) -> str:
    """``AAPL.NASDAQ`` → ``AAPL``. Plain tickers pass through unchanged."""
    vt = (vt_symbol or "").strip().upper()
    if not vt:
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "vt_symbol is required",
                "hint": "Pass the ticker as the path segment, e.g. /data/security/AAPL/fundamentals.",
                "code": "missing_symbol",
            },
        )
    if "." in vt:
        return vt.split(".")[0]
    return vt


def _require_yfinance() -> None:
    try:
        import yfinance  # noqa: F401
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "yfinance is not installed in this environment.",
                "hint": "pip install yfinance or install aqp[dev]",
                "code": "yfinance_missing",
            },
        ) from exc


def _wrap_provider_error(ticker: str, exc: Exception) -> HTTPException:
    """Translate a provider failure into a structured 404/502 response."""
    message = str(exc) or exc.__class__.__name__
    lowered = message.lower()
    if "yfinance" in lowered and ("not installed" in lowered or "no module named" in lowered):
        return HTTPException(
            status_code=503,
            detail={
                "detail": "yfinance is not installed in this environment.",
                "hint": "pip install yfinance or install aqp[dev]",
                "code": "yfinance_missing",
            },
        )
    if "no fundamentals payload" in lowered or "no quote snapshot" in lowered:
        return HTTPException(
            status_code=404,
            detail={
                "detail": f"No data returned for {ticker!r}.",
                "hint": "Check the symbol, or try again later — yfinance occasionally drops payloads on rate-limit.",
                "code": "empty_payload",
            },
        )
    logger.warning("provider error for %s: %s", ticker, message)
    return HTTPException(
        status_code=502,
        detail={
            "detail": f"Upstream provider failed: {message}",
            "hint": "Retry later; if it persists, the yfinance endpoint is likely rate-limited.",
            "code": "provider_error",
        },
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{vt_symbol}/fundamentals", response_model=FundamentalsResponse)
async def fundamentals(vt_symbol: str) -> FundamentalsResponse:
    """Full fundamentals payload. Cached for 1 hour."""
    ticker = _ticker_from_vt(vt_symbol)

    from aqp.data.cache import cache_get
    was_cached = cache_get(_SCOPE_FUNDAMENTALS, ticker) is not None

    def _producer() -> dict[str, Any]:
        from aqp.data.fundamentals import resolve_fundamentals_one

        return resolve_fundamentals_one(ticker)

    try:
        payload = await cached_json(_SCOPE_FUNDAMENTALS, ticker, _TTL_FUNDAMENTALS, _producer)
    except Exception as exc:
        raise _wrap_provider_error(ticker, exc) from exc

    return FundamentalsResponse(**payload, cached=was_cached)


@router.get("/{vt_symbol}/news", response_model=NewsResponse)
async def news(
    vt_symbol: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> NewsResponse:
    """Recent headlines. Cached for 15 minutes."""
    _require_yfinance()
    ticker = _ticker_from_vt(vt_symbol)
    cache_key = f"{ticker}:{limit}"

    from aqp.data.cache import cache_get
    was_cached = cache_get(_SCOPE_NEWS, cache_key) is not None

    def _producer() -> dict[str, Any]:
        from aqp.data.ingestion import YahooFinanceSource

        return {
            "ticker": ticker,
            "items": YahooFinanceSource().fetch_news(ticker, limit=limit),
        }

    try:
        payload = await cached_json(_SCOPE_NEWS, cache_key, _TTL_NEWS, _producer)
    except Exception as exc:
        raise _wrap_provider_error(ticker, exc) from exc

    items = [NewsItem(**item) for item in payload.get("items", [])]
    return NewsResponse(
        ticker=payload["ticker"],
        count=len(items),
        items=items,
        cached=was_cached,
    )


@router.get("/{vt_symbol}/calendar", response_model=CalendarResponse)
async def calendar(vt_symbol: str) -> CalendarResponse:
    """Upcoming earnings + dividend calendar. Cached for 1 hour."""
    _require_yfinance()
    ticker = _ticker_from_vt(vt_symbol)

    from aqp.data.cache import cache_get
    was_cached = cache_get(_SCOPE_CALENDAR, ticker) is not None

    def _producer() -> dict[str, Any]:
        from aqp.data.ingestion import YahooFinanceSource

        return YahooFinanceSource().fetch_calendar(ticker)

    try:
        payload = await cached_json(_SCOPE_CALENDAR, ticker, _TTL_CALENDAR, _producer)
    except Exception as exc:
        raise _wrap_provider_error(ticker, exc) from exc

    # Flatten well-known fields; the rest stays in ``raw`` for debugging.
    known_keys = {
        "ticker",
        "earnings_date",
        "ex_dividend_date",
        "dividend_date",
        "earnings_high",
        "earnings_low",
        "earnings_average",
        "revenue_high",
        "revenue_low",
        "revenue_average",
        "earnings_history",
    }
    raw = {k: v for k, v in payload.items() if k not in known_keys}
    return CalendarResponse(
        ticker=payload.get("ticker", ticker),
        earnings_date=payload.get("earnings_date"),
        ex_dividend_date=payload.get("ex_dividend_date"),
        dividend_date=payload.get("dividend_date"),
        earnings_high=payload.get("earnings_high"),
        earnings_low=payload.get("earnings_low"),
        earnings_average=payload.get("earnings_average"),
        revenue_high=payload.get("revenue_high"),
        revenue_low=payload.get("revenue_low"),
        revenue_average=payload.get("revenue_average"),
        earnings_history=payload.get("earnings_history", []),
        raw=raw,
        cached=was_cached,
    )


@router.get("/{vt_symbol}/corporate", response_model=CorporateActionsResponse)
async def corporate(vt_symbol: str) -> CorporateActionsResponse:
    """Dividends, splits, institutional holders. Cached for 6 hours."""
    _require_yfinance()
    ticker = _ticker_from_vt(vt_symbol)

    from aqp.data.cache import cache_get
    was_cached = cache_get(_SCOPE_CORPORATE, ticker) is not None

    def _producer() -> dict[str, Any]:
        from aqp.data.ingestion import YahooFinanceSource

        return YahooFinanceSource().fetch_corporate_actions(ticker)

    try:
        payload = await cached_json(_SCOPE_CORPORATE, ticker, _TTL_CORPORATE, _producer)
    except Exception as exc:
        raise _wrap_provider_error(ticker, exc) from exc

    return CorporateActionsResponse(**payload, cached=was_cached)


@router.get("/{vt_symbol}/quote", response_model=QuoteSnapshot)
async def quote(vt_symbol: str) -> QuoteSnapshot:
    """Live-ish snapshot quote. Cached for 5 seconds (tight polling window)."""
    _require_yfinance()
    ticker = _ticker_from_vt(vt_symbol)

    from aqp.data.cache import cache_get
    was_cached = cache_get(_SCOPE_QUOTE, ticker) is not None

    def _producer() -> dict[str, Any]:
        from aqp.data.ingestion import YahooFinanceSource

        return YahooFinanceSource().fetch_quote(ticker)

    try:
        payload = await cached_json(_SCOPE_QUOTE, ticker, _TTL_QUOTE, _producer)
    except Exception as exc:
        raise _wrap_provider_error(ticker, exc) from exc

    return QuoteSnapshot(**payload, cached=was_cached)


# ---------------------------------------------------------------------------
# Cache admin (not exposed by default, but handy during incident response).
# ---------------------------------------------------------------------------


@router.delete("/{vt_symbol}/cache")
def invalidate_cache(vt_symbol: str) -> JSONResponse:
    """Flush all cached facets for a single ticker."""
    from aqp.data.cache import cache_invalidate

    ticker = _ticker_from_vt(vt_symbol)
    removed = 0
    for scope in (
        _SCOPE_FUNDAMENTALS,
        _SCOPE_NEWS,
        _SCOPE_CALENDAR,
        _SCOPE_CORPORATE,
        _SCOPE_QUOTE,
    ):
        # News is keyed with limit suffix; invalidate the scope slice for news.
        if scope == _SCOPE_NEWS:
            # Loop common limit values used by the UI (20 + 50).
            for limit in (20, 50):
                removed += cache_invalidate(scope, f"{ticker}:{limit}")
        else:
            removed += cache_invalidate(scope, ticker)
    return JSONResponse({"ticker": ticker, "removed": removed})


@router.get("/{vt_symbol}/cache/info")
def cache_info(vt_symbol: str) -> dict[str, Any]:
    """Inspect cached facets for a ticker.

    Returns per-scope hit / TTL information so the Data Browser can show
    a "what's cached" panel. Best-effort: missing Redis or unreachable
    cache returns ``{ scopes: [], available: false }``.
    """
    ticker = _ticker_from_vt(vt_symbol)
    out: list[dict[str, Any]] = []
    available = True
    try:
        from aqp.data.cache import _scoped_key, _sync_client  # type: ignore[attr-defined]

        client = _sync_client()
        scopes: list[tuple[str, str]] = [
            (_SCOPE_FUNDAMENTALS, ticker),
            (_SCOPE_CALENDAR, ticker),
            (_SCOPE_CORPORATE, ticker),
            (_SCOPE_QUOTE, ticker),
            (_SCOPE_NEWS, f"{ticker}:20"),
            (_SCOPE_NEWS, f"{ticker}:50"),
        ]
        for scope, key in scopes:
            full = _scoped_key(scope, key)
            try:
                ttl = int(client.ttl(full))
                exists = bool(client.exists(full))
            except Exception:
                ttl = -2
                exists = False
            out.append(
                {
                    "scope": scope,
                    "key": key,
                    "redis_key": full,
                    "cached": exists,
                    "ttl_seconds": ttl,
                }
            )
    except Exception:
        available = False

    return {
        "ticker": ticker,
        "vt_symbol": vt_symbol,
        "available": available,
        "scopes": out,
    }
