"""Paper / live trading endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import Fill, LedgerEntry, OrderRecord, PaperTradingRun
from aqp.tasks.paper_tasks import publish_stop_signal, run_paper

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paper", tags=["paper"])


class PaperRunRequest(BaseModel):
    config: dict[str, Any]
    run_name: str = Field(default="paper-adhoc")


class PaperRunSummary(BaseModel):
    id: str
    task_id: str | None = None
    run_name: str
    strategy_id: str | None = None
    brokerage: str
    feed: str
    status: str
    started_at: str | None = None
    stopped_at: str | None = None
    last_heartbeat_at: str | None = None
    initial_cash: float | None = None
    final_equity: float | None = None
    realized_pnl: float | None = None
    bars_seen: int = 0
    orders_submitted: int = 0
    fills: int = 0
    error: str | None = None


class PaperRunDetail(PaperRunSummary):
    config: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    recent_orders: list[dict[str, Any]] = Field(default_factory=list)
    recent_fills: list[dict[str, Any]] = Field(default_factory=list)
    recent_ledger: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/start", response_model=TaskAccepted)
def start_paper(req: PaperRunRequest) -> TaskAccepted:
    async_result = run_paper.delay(req.config, req.run_name)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.post("/stop/{task_id}")
def stop_paper(task_id: str, reason: str = "manual") -> dict[str, Any]:
    publish_stop_signal(task_id, reason=reason)
    return {"task_id": task_id, "reason": reason, "ok": True}


@router.get("/runs", response_model=list[PaperRunSummary])
def list_paper_runs(limit: int = 50) -> list[PaperRunSummary]:
    with get_session() as s:
        rows = s.execute(
            select(PaperTradingRun)
            .order_by(desc(PaperTradingRun.started_at))
            .limit(limit)
        ).scalars().all()
        return [_to_summary(r) for r in rows]


@router.get("/runs/{run_id}", response_model=PaperRunDetail)
def get_paper_run(run_id: str) -> PaperRunDetail:
    with get_session() as s:
        row = s.get(PaperTradingRun, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"no paper run {run_id}")
        ref = f"paper:{row.id}"
        recent_orders = s.execute(
            select(OrderRecord)
            .where(OrderRecord.reference == ref)
            .order_by(desc(OrderRecord.created_at))
            .limit(25)
        ).scalars().all()
        order_ids = [o.id for o in recent_orders]
        recent_fills: list[Fill] = []
        if order_ids:
            recent_fills = s.execute(
                select(Fill)
                .where(Fill.order_id.in_(order_ids))
                .order_by(desc(Fill.created_at))
                .limit(50)
            ).scalars().all()
        recent_ledger = s.execute(
            select(LedgerEntry)
            .order_by(desc(LedgerEntry.created_at))
            .limit(50)
        ).scalars().all()
        detail = _to_summary(row).model_dump()
        detail.update(
            {
                "config": row.config or {},
                "state": row.state or {},
                "recent_orders": [_order_dict(o) for o in recent_orders],
                "recent_fills": [_fill_dict(f) for f in recent_fills],
                "recent_ledger": [_ledger_dict(le) for le in recent_ledger],
            }
        )
        return PaperRunDetail(**detail)


def _to_summary(row: PaperTradingRun) -> PaperRunSummary:
    return PaperRunSummary(
        id=row.id,
        task_id=row.task_id,
        run_name=row.run_name,
        strategy_id=row.strategy_id,
        brokerage=row.brokerage,
        feed=row.feed,
        status=row.status,
        started_at=row.started_at.isoformat() if row.started_at else None,
        stopped_at=row.stopped_at.isoformat() if row.stopped_at else None,
        last_heartbeat_at=row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
        initial_cash=row.initial_cash,
        final_equity=row.final_equity,
        realized_pnl=row.realized_pnl,
        bars_seen=row.bars_seen,
        orders_submitted=row.orders_submitted,
        fills=row.fills,
        error=row.error,
    )


def _order_dict(o: OrderRecord) -> dict[str, Any]:
    return {
        "id": o.id,
        "vt_symbol": o.vt_symbol,
        "side": o.side,
        "order_type": o.order_type,
        "quantity": o.quantity,
        "price": o.price,
        "status": o.status,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def _fill_dict(f: Fill) -> dict[str, Any]:
    return {
        "id": f.id,
        "order_id": f.order_id,
        "vt_symbol": f.vt_symbol,
        "side": f.side,
        "quantity": f.quantity,
        "price": f.price,
        "commission": f.commission,
        "slippage": f.slippage,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _ledger_dict(le: LedgerEntry) -> dict[str, Any]:
    return {
        "id": le.id,
        "type": le.entry_type,
        "level": le.level,
        "message": le.message,
        "payload": le.payload,
        "created_at": le.created_at.isoformat() if le.created_at else None,
    }
