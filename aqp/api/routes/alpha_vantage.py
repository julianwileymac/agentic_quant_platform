"""Alpha Vantage data/provider API surface."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from aqp.services.alpha_vantage_service import AlphaVantageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/alpha-vantage", tags=["alpha-vantage"])

_SERVICE: AlphaVantageService | None = None


class AlphaVantageHealth(BaseModel):
    enabled: bool
    credentials_loaded: bool
    base_url: str
    rpm_limit: int
    daily_limit: int
    cache_backend: str
    client_version: str | None = None
    client_available: bool = True
    message: str | None = None


class AlphaVantageUsage(BaseModel):
    rpm_limit: int
    daily_limit: int
    requests_this_minute: int
    requests_today: int
    tokens_available: float
    next_refill_seconds: float
    daily_reset_utc: str


class BulkLoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(
        description=(
            "timeseries | fundamentals | universe | news | earnings | "
            "technicals | options"
        ),
    )
    symbols: list[str] = Field(default_factory=list)
    date_range: dict[str, str] | None = None
    extra_params: dict[str, Any] = Field(default_factory=dict)
    target_bucket: str | None = Field(
        default=None,
        description="Optional local target root. Defaults to AQP_DATA_DIR/alpha_vantage/raw.",
    )


class BulkLoadQueued(BaseModel):
    task_id: str
    status: str = "queued"
    stream_url: str
    submitted_at: str
    category: str
    symbols: list[str]


def get_alpha_vantage_service() -> AlphaVantageService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = AlphaVantageService()
    return _SERVICE


def _guard_enabled(service: AlphaVantageService) -> None:
    if not service.enabled:
        raise HTTPException(status_code=503, detail="Alpha Vantage integration disabled")


@router.get("/health", response_model=AlphaVantageHealth)
async def health(service: AlphaVantageService = Depends(get_alpha_vantage_service)) -> AlphaVantageHealth:
    return AlphaVantageHealth(**await service.health())


@router.get("/usage", response_model=AlphaVantageUsage)
async def usage(service: AlphaVantageService = Depends(get_alpha_vantage_service)) -> AlphaVantageUsage:
    _guard_enabled(service)
    return AlphaVantageUsage(**await service.usage())


@router.get("/search")
async def search(
    keywords: str = Query(..., min_length=1),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> list[dict[str, Any]]:
    _guard_enabled(service)
    return await service.symbol_search(keywords)


@router.get("/market-status")
async def market_status(service: AlphaVantageService = Depends(get_alpha_vantage_service)) -> dict[str, Any]:
    _guard_enabled(service)
    return await service.market_status()


@router.get("/timeseries/{function}")
async def timeseries(
    function: str,
    symbol: str = Query(..., min_length=1),
    interval: str | None = Query(default=None),
    outputsize: str | None = Query(default=None),
    month: str | None = Query(default=None),
    adjusted: bool | None = Query(default=None),
    extended_hours: bool | None = Query(default=None),
    entitlement: str | None = Query(default=None),
    symbols: str | None = Query(default=None, description="Comma-separated symbols for bulk quotes"),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    params: dict[str, Any] = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "month": month,
        "adjusted": adjusted,
        "extended_hours": extended_hours,
        "entitlement": entitlement,
    }
    if function == "bulk_quotes":
        params["symbols"] = [s.strip() for s in (symbols or symbol).split(",") if s.strip()]
    try:
        return await service.timeseries(function, **params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/fundamentals/{kind}")
async def fundamentals(
    kind: str,
    symbol: str | None = Query(default=None),
    horizon: str | None = Query(default=None),
    date: str | None = Query(default=None),
    state: str | None = Query(default=None),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    try:
        result = await service.fundamentals(
            kind,
            symbol=symbol,
            horizon=horizon,
            date=date,
            state=state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(result, str):
        return PlainTextResponse(result, media_type="text/csv")
    return result


@router.get("/technicals/{indicator}")
async def technicals(
    indicator: str,
    symbol: str = Query(..., min_length=1),
    interval: str = Query(default="daily"),
    time_period: int | None = Query(default=20),
    series_type: str | None = Query(default="close"),
    month: str | None = Query(default=None),
    entitlement: str | None = Query(default=None),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    try:
        return await service.technicals(
            indicator,
            symbol,
            interval=interval,
            time_period=time_period,
            series_type=series_type,
            month=month,
            entitlement=entitlement,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/intelligence/{kind}")
async def intelligence(
    kind: str,
    tickers: str | None = Query(default=None),
    topics: str | None = Query(default=None),
    time_from: str | None = Query(default=None),
    time_to: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    symbol: str | None = Query(default=None),
    quarter: str | None = Query(default=None),
    entitlement: str | None = Query(default=None),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    params: dict[str, Any] = {
        "tickers": tickers,
        "topics": topics,
        "time_from": time_from,
        "time_to": time_to,
        "sort": sort,
        "limit": limit,
        "symbol": symbol,
        "quarter": quarter,
        "entitlement": entitlement,
    }
    try:
        return await service.intelligence(kind, **params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/forex/{kind}")
async def forex(
    kind: str,
    from_currency: str | None = Query(default=None, alias="from"),
    to_currency: str | None = Query(default=None, alias="to"),
    from_symbol: str | None = None,
    to_symbol: str | None = None,
    interval: str | None = None,
    outputsize: str | None = None,
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    try:
        return await service.forex(
            kind,
            from_currency=from_currency,
            to_currency=to_currency,
            from_symbol=from_symbol or from_currency,
            to_symbol=to_symbol or to_currency,
            interval=interval,
            outputsize=outputsize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/crypto/{kind}")
async def crypto(
    kind: str,
    symbol: str = Query(..., min_length=1),
    market: str = Query(default="USD"),
    interval: str | None = Query(default=None),
    outputsize: str | None = Query(default=None),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    try:
        return await service.crypto(
            kind,
            symbol=symbol,
            market=market,
            interval=interval,
            outputsize=outputsize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/options/{kind}")
async def options(
    kind: str,
    symbol: str = Query(..., min_length=1),
    contract: str | None = Query(default=None),
    date: str | None = Query(default=None),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    try:
        return await service.options(kind, symbol=symbol, contract=contract, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/commodities/{commodity}")
async def commodities(
    commodity: str,
    interval: str = Query(default="monthly"),
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    return await service.commodities(commodity, interval=interval)


@router.get("/economics/{indicator}")
async def economics(
    indicator: str,
    interval: str | None = None,
    maturity: str | None = None,
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    return await service.economics(indicator, interval=interval, maturity=maturity)


@router.get("/indices/catalog")
async def indices_catalog(service: AlphaVantageService = Depends(get_alpha_vantage_service)) -> Any:
    _guard_enabled(service)
    return await service.index_catalog()


@router.get("/indices/{name}")
async def indices(
    name: str,
    interval: str | None = None,
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> Any:
    _guard_enabled(service)
    return await service.indices(name, interval=interval)


@router.post("/bulk-load", response_model=BulkLoadQueued)
async def bulk_load(
    payload: BulkLoadRequest,
    service: AlphaVantageService = Depends(get_alpha_vantage_service),
) -> BulkLoadQueued:
    _guard_enabled(service)
    try:
        result = service.submit_bulk_task(
            category=payload.category,
            symbols=payload.symbols,
            date_range=payload.date_range,
            extra_params=payload.extra_params,
            target_bucket=payload.target_bucket,
        )
        return BulkLoadQueued(**result)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Alpha Vantage bulk-load submission failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/bulk-categories")
async def bulk_categories() -> dict[str, list[str]]:
    return {
        "categories": [
            "timeseries",
            "fundamentals",
            "universe",
            "news",
            "earnings",
            "technicals",
            "options",
        ],
    }


__all__ = ["router"]
