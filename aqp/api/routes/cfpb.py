"""REST endpoints for the CFPB Consumer Complaint Database adapter."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.tasks.regulatory_tasks import ingest_cfpb_complaints

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cfpb", tags=["cfpb", "regulatory"])


class CfpbProbeResponse(BaseModel):
    ok: bool
    message: str
    endpoint: str


class CfpbIngestRequest(BaseModel):
    company: str | None = None
    product: str | None = None
    date_received_min: str | None = Field(default=None, description="YYYY-MM-DD")
    date_received_max: str | None = Field(default=None, description="YYYY-MM-DD")
    has_narrative: bool | None = None
    max_records: int | None = Field(default=5000, ge=1, le=100_000)
    vt_symbol: str | None = None


class CfpbComplaintRow(BaseModel):
    complaint_id: str
    company: str
    product: str | None = None
    issue: str | None = None
    state: str | None = None
    date_received: str | None = None
    has_narrative: bool


@router.get("/probe", response_model=CfpbProbeResponse)
def cfpb_probe() -> CfpbProbeResponse:
    from aqp.data.sources.cfpb import CfpbClient

    with CfpbClient() as client:
        ok, message = client.probe()
        return CfpbProbeResponse(ok=ok, message=message, endpoint=client.base_url)


@router.get("/search")
def cfpb_search(
    company: str | None = Query(default=None),
    product: str | None = Query(default=None),
    date_received_min: str | None = Query(default=None),
    date_received_max: str | None = Query(default=None),
    has_narrative: bool | None = Query(default=None),
    size: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    from aqp.data.sources.cfpb import CfpbClient

    with CfpbClient() as client:
        try:
            page = client.search_page(
                company=company,
                product=product,
                date_received_min=date_received_min,
                date_received_max=date_received_max,
                has_narrative=has_narrative,
                size=size,
                frm=0,
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    hits_root = page.get("hits") or {}
    hits = hits_root.get("hits") if isinstance(hits_root, dict) else hits_root
    return {"count": len(hits or []), "hits": hits or []}


@router.post("/ingest", response_model=TaskAccepted, status_code=202)
def cfpb_ingest(req: CfpbIngestRequest) -> TaskAccepted:
    task = ingest_cfpb_complaints.delay(
        company=req.company,
        product=req.product,
        date_received_min=req.date_received_min,
        date_received_max=req.date_received_max,
        has_narrative=req.has_narrative,
        max_records=req.max_records,
        vt_symbol=req.vt_symbol,
    )
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.get("/complaints", response_model=list[CfpbComplaintRow])
def cfpb_complaints(
    company: str | None = Query(default=None),
    product: str | None = Query(default=None),
    state: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[CfpbComplaintRow]:
    from aqp.persistence.models_regulatory import CfpbComplaint

    with get_session() as session:
        stmt = select(CfpbComplaint)
        if company:
            stmt = stmt.where(CfpbComplaint.company == company)
        if product:
            stmt = stmt.where(CfpbComplaint.product == product)
        if state:
            stmt = stmt.where(CfpbComplaint.state == state)
        stmt = stmt.order_by(desc(CfpbComplaint.date_received)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        CfpbComplaintRow(
            complaint_id=r.complaint_id,
            company=r.company,
            product=r.product,
            issue=r.issue,
            state=r.state,
            date_received=str(r.date_received) if r.date_received else None,
            has_narrative=bool(r.has_narrative),
        )
        for r in rows
    ]
