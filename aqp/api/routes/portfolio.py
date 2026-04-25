"""Portfolio + ledger + live monitoring endpoints."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import desc, select

from aqp.api.schemas import KillSwitchRequest
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, LedgerEntry, OrderRecord
from aqp.risk.kill_switch import engage, release, status
from aqp.services.portfolio_service import (
    compute_allocations,
    compute_exposures,
    compute_pnl_series,
    compute_positions,
    compute_risk,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/orders")
def list_orders(limit: int = 100) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            select(OrderRecord).order_by(desc(OrderRecord.created_at)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "vt_symbol": r.vt_symbol,
                "side": r.side,
                "order_type": r.order_type,
                "quantity": r.quantity,
                "price": r.price,
                "status": r.status,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]


@router.get("/fills")
def list_fills(limit: int = 100) -> list[dict]:
    with get_session() as s:
        rows = s.execute(
            select(Fill).order_by(desc(Fill.created_at)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "vt_symbol": r.vt_symbol,
                "side": r.side,
                "quantity": r.quantity,
                "price": r.price,
                "commission": r.commission,
                "slippage": r.slippage,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]


@router.get("/ledger")
def list_ledger(limit: int = 200, entry_type: str | None = None) -> list[dict]:
    with get_session() as s:
        stmt = select(LedgerEntry).order_by(desc(LedgerEntry.created_at)).limit(limit)
        if entry_type:
            stmt = stmt.where(LedgerEntry.entry_type == entry_type)
        rows = s.execute(stmt).scalars().all()
        return [
            {
                "id": r.id,
                "type": r.entry_type,
                "level": r.level,
                "message": r.message,
                "payload": r.payload,
                "created_at": str(r.created_at),
            }
            for r in rows
        ]


@router.get("/kill_switch")
def kill_switch_status() -> dict:
    return status()


@router.post("/kill_switch")
def kill_switch_toggle(req: KillSwitchRequest) -> dict:
    if req.engage:
        engage(req.reason)
    else:
        release()
    return status()


# ---------------------------------------------------------------------------
# Live monitoring — positions / PnL / allocations / exposures / risk
# ---------------------------------------------------------------------------


@router.get("/positions")
def get_positions(
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    return compute_positions(start=_parse_dt(start), end=_parse_dt(end))


@router.get("/pnl")
def get_pnl(
    start: str | None = None,
    end: str | None = None,
    initial_cash: float = 0.0,
) -> dict[str, Any]:
    return compute_pnl_series(
        start=_parse_dt(start),
        end=_parse_dt(end),
        initial_cash=float(initial_cash),
    )


@router.get("/allocations")
def get_allocations(
    by: str = Query(default="sector"),
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    return compute_allocations(by=by, start=_parse_dt(start), end=_parse_dt(end))


@router.get("/exposures")
def get_exposures(
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    return compute_exposures(start=_parse_dt(start), end=_parse_dt(end))


@router.get("/risk")
def get_risk(
    start: str | None = None,
    end: str | None = None,
    initial_cash: float = 0.0,
    benchmark_vt_symbol: str | None = None,
) -> dict[str, Any]:
    return compute_risk(
        start=_parse_dt(start),
        end=_parse_dt(end),
        initial_cash=float(initial_cash),
        benchmark_vt_symbol=benchmark_vt_symbol,
    )
