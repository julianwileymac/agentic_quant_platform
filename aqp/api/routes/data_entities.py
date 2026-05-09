"""Data-product entity routes.

Backs the unified Data Hub UI's "Entities" tab. Each route returns a
:class:`aqp.data.products.BaseDataProduct` context-pack as JSON.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data/entities", tags=["data-entities"])


@router.get("/{vt_symbol}")
def equity_entity(
    vt_symbol: str,
    *,
    bars_lookback_days: int = Query(default=30, ge=1, le=365),
    max_tokens: int | None = Query(default=4000, ge=200, le=64000),
) -> dict[str, Any]:
    """Return the :class:`EquityEntity` context pack for one ``vt_symbol``."""
    from aqp.data.products import EquityEntity

    try:
        product = EquityEntity(vt_symbol, bars_lookback_days=bars_lookback_days)
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.exception("equity entity load failed for %s", vt_symbol)
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{vt_symbol}/option-chain")
def option_chain_entity(
    vt_symbol: str,
    *,
    max_strikes: int = Query(default=50, ge=1, le=500),
    max_tokens: int | None = Query(default=4000, ge=200, le=64000),
) -> dict[str, Any]:
    from aqp.data.products import OptionChainEntity

    try:
        product = OptionChainEntity(vt_symbol, max_strikes=max_strikes)
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/macro/{series_id}")
def macro_series_entity(
    series_id: str,
    *,
    recent_observations: int = Query(default=60, ge=1, le=600),
    max_tokens: int | None = Query(default=4000, ge=200, le=64000),
) -> dict[str, Any]:
    from aqp.data.products import MacroSeriesEntity

    try:
        product = MacroSeriesEntity(series_id, recent_observations=recent_observations)
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/regulatory/{vt_symbol}")
def regulatory_entity(
    vt_symbol: str,
    *,
    per_table_limit: int = Query(default=10, ge=1, le=100),
    max_tokens: int | None = Query(default=4000, ge=200, le=64000),
) -> dict[str, Any]:
    from aqp.data.products import RegulatoryEntity

    try:
        product = RegulatoryEntity(vt_symbol, per_table_limit=per_table_limit)
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/portfolio/{portfolio_id}")
def portfolio_entity(
    portfolio_id: str,
    *,
    recent_fills: int = Query(default=10, ge=1, le=100),
    max_tokens: int | None = Query(default=4000, ge=200, le=64000),
) -> dict[str, Any]:
    from aqp.data.products import PortfolioEntity

    try:
        product = PortfolioEntity(portfolio_id, recent_fills=recent_fills)
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/graph/{root_vt_symbol}")
def instrument_graph(
    root_vt_symbol: str,
    *,
    depth: int = Query(default=2, ge=1, le=5),
    max_nodes: int = Query(default=50, ge=1, le=500),
    max_tokens: int | None = Query(default=6000, ge=200, le=64000),
) -> dict[str, Any]:
    from aqp.data.products import InstrumentGraphProduct

    try:
        product = InstrumentGraphProduct(
            root_vt_symbol, depth=depth, max_nodes=max_nodes
        )
        return product.to_context_pack(max_tokens=max_tokens)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=str(exc)) from exc


__all__ = ["router"]
