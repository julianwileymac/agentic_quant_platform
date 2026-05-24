"""Alpha Vantage API router.

Exposes the full Alpha Vantage surface (time series, fundamentals, options,
forex, crypto, commodities, economics, technical indicators, alpha intelligence,
indices) plus admin endpoints for bulk-load workflow submission and streaming
producer toggling. All handlers delegate to :class:`AlphaVantageService`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..config import Settings, get_settings
from ..models.alphavantage import (
    AlphaVantageHealth,
    AlphaVantageUsage,
    BulkLoadRequest,
    BulkLoadResponse,
    StreamToggleRequest,
    StreamToggleResponse,
)
from ..services.alphavantage_service import AlphaVantageService

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Service dependency (cached per app instance)
# ---------------------------------------------------------------------------


_SERVICE_SINGLETON: Optional[AlphaVantageService] = None


def get_av_service(settings: Settings = Depends(get_settings)) -> AlphaVantageService:
    global _SERVICE_SINGLETON
    if _SERVICE_SINGLETON is None:
        _SERVICE_SINGLETON = AlphaVantageService(settings)
    return _SERVICE_SINGLETON


def _guard_enabled(service: AlphaVantageService) -> None:
    if not service.cfg.enabled:
        raise HTTPException(status_code=503, detail="Alpha Vantage integration disabled")


# ---------------------------------------------------------------------------
# Health / usage / utilities
# ---------------------------------------------------------------------------


@router.get("/health", response_model=AlphaVantageHealth)
async def health(service: AlphaVantageService = Depends(get_av_service)) -> AlphaVantageHealth:
    payload = await service.health()
    return AlphaVantageHealth(**payload)


@router.get("/usage", response_model=AlphaVantageUsage)
async def usage(service: AlphaVantageService = Depends(get_av_service)) -> AlphaVantageUsage:
    _guard_enabled(service)
    payload = await service.usage()
    return AlphaVantageUsage(**payload)


@router.get("/search")
async def search(
    keywords: str = Query(..., min_length=1),
    service: AlphaVantageService = Depends(get_av_service),
) -> List[Dict[str, Any]]:
    _guard_enabled(service)
    return await service.symbol_search(keywords)


@router.get("/market-status")
async def market_status(service: AlphaVantageService = Depends(get_av_service)) -> Dict[str, Any]:
    _guard_enabled(service)
    return await service.market_status()


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------


@router.get("/timeseries/{function}")
async def timeseries(
    function: str,
    symbol: str = Query(..., min_length=1),
    interval: Optional[str] = Query(default=None),
    outputsize: Optional[str] = Query(default=None),
    month: Optional[str] = Query(default=None),
    adjusted: Optional[bool] = Query(default=None),
    extended_hours: Optional[bool] = Query(default=None),
    entitlement: Optional[str] = Query(default=None),
    symbols: Optional[str] = Query(default=None, description="Comma-separated for bulk quotes"),
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    params: Dict[str, Any] = {
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


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------


@router.get("/fundamentals/{kind}")
async def fundamentals(
    kind: str,
    symbol: Optional[str] = Query(default=None),
    horizon: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    service: AlphaVantageService = Depends(get_av_service),
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
    # Calendar / listing endpoints return CSV text.
    if isinstance(result, str):
        return PlainTextResponse(result, media_type="text/csv")
    return result


# ---------------------------------------------------------------------------
# Technical indicators
# ---------------------------------------------------------------------------


@router.get("/technicals/{indicator}")
async def technicals(
    indicator: str,
    symbol: str = Query(..., min_length=1),
    interval: str = Query(default="daily"),
    time_period: Optional[int] = Query(default=20),
    series_type: Optional[str] = Query(default="close"),
    month: Optional[str] = Query(default=None),
    entitlement: Optional[str] = Query(default=None),
    service: AlphaVantageService = Depends(get_av_service),
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


# ---------------------------------------------------------------------------
# Alpha Intelligence
# ---------------------------------------------------------------------------


@router.get("/intelligence/{kind}")
async def intelligence(
    kind: str,
    tickers: Optional[str] = Query(default=None),
    topics: Optional[str] = Query(default=None),
    time_from: Optional[str] = Query(default=None),
    time_to: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default=None),
    limit: Optional[int] = Query(default=None, ge=1, le=1000),
    symbol: Optional[str] = Query(default=None),
    quarter: Optional[str] = Query(default=None),
    entitlement: Optional[str] = Query(default=None),
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    params: Dict[str, Any] = {
        "tickers": [t.strip() for t in tickers.split(",")] if tickers else None,
        "topics": [t.strip() for t in topics.split(",")] if topics else None,
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


# ---------------------------------------------------------------------------
# Forex / Crypto / Options
# ---------------------------------------------------------------------------


@router.get("/forex/{kind}")
async def forex(
    kind: str,
    from_currency: Optional[str] = Query(default=None, alias="from"),
    to_currency: Optional[str] = Query(default=None, alias="to"),
    from_symbol: Optional[str] = None,
    to_symbol: Optional[str] = None,
    interval: Optional[str] = None,
    outputsize: Optional[str] = None,
    service: AlphaVantageService = Depends(get_av_service),
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
    interval: Optional[str] = Query(default=None),
    outputsize: Optional[str] = Query(default=None),
    service: AlphaVantageService = Depends(get_av_service),
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
    contract: Optional[str] = Query(default=None),
    date: Optional[str] = Query(default=None),
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    try:
        return await service.options(kind, symbol=symbol, contract=contract, date=date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Commodities, economics, indices
# ---------------------------------------------------------------------------


@router.get("/commodities/{commodity}")
async def commodities(
    commodity: str,
    interval: str = Query(default="monthly"),
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    return await service.commodities(commodity, interval=interval)


@router.get("/economics/{indicator}")
async def economics(
    indicator: str,
    interval: Optional[str] = None,
    maturity: Optional[str] = None,
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    return await service.economics(indicator, interval=interval, maturity=maturity)


@router.get("/indices/catalog")
async def indices_catalog(service: AlphaVantageService = Depends(get_av_service)) -> Any:
    _guard_enabled(service)
    return await service.index_catalog()


@router.get("/indices/{name}")
async def indices(
    name: str,
    interval: Optional[str] = None,
    service: AlphaVantageService = Depends(get_av_service),
) -> Any:
    _guard_enabled(service)
    return await service.indices(name, interval=interval)


# ---------------------------------------------------------------------------
# Bulk-load + streaming controls
# ---------------------------------------------------------------------------


@router.post("/bulk-load", response_model=BulkLoadResponse)
async def bulk_load(
    payload: BulkLoadRequest,
    service: AlphaVantageService = Depends(get_av_service),
) -> BulkLoadResponse:
    _guard_enabled(service)
    try:
        result = await service.submit_bulk_workflow(
            category=payload.category,
            symbols=payload.symbols,
            date_range=payload.date_range,
            extra_params=payload.extra_params,
            target_bucket=payload.target_bucket,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("bulk-load submission failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return BulkLoadResponse(**result)


@router.get("/workflows")
async def workflows(
    limit: int = Query(default=25, ge=1, le=200),
    service: AlphaVantageService = Depends(get_av_service),
) -> List[Dict[str, Any]]:
    _guard_enabled(service)
    try:
        return await service.list_workflows(limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("workflow list failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/stream", response_model=StreamToggleResponse)
async def stream_toggle(
    payload: StreamToggleRequest,
    service: AlphaVantageService = Depends(get_av_service),
) -> StreamToggleResponse:
    _guard_enabled(service)
    try:
        result = await service.toggle_stream(
            enable=payload.enable,
            replicas=payload.replicas,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("stream toggle failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return StreamToggleResponse(**result)


__all__ = ["router"]
