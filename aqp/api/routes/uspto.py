"""REST endpoints for the USPTO adapter (PatentsView, TSDR, PEDS)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.tasks.regulatory_tasks import (
    ingest_uspto_assignments,
    ingest_uspto_patents,
    ingest_uspto_trademarks,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uspto", tags=["uspto", "regulatory"])


class UsptoProbeResponse(BaseModel):
    ok: bool
    message: str


class UsptoPatentIngestRequest(BaseModel):
    assignee: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    max_records: int | None = Field(default=5000, ge=1, le=50_000)
    vt_symbol: str | None = None


class UsptoTrademarkIngestRequest(BaseModel):
    serial_numbers: list[str] = Field(..., min_length=1)
    vt_symbol: str | None = None


class UsptoAssignmentIngestRequest(BaseModel):
    search_text: str = Field(default="*:*")
    max_records: int | None = Field(default=5000, ge=1, le=50_000)
    vt_symbol: str | None = None


@router.get("/probe", response_model=UsptoProbeResponse)
def uspto_probe() -> UsptoProbeResponse:
    from aqp.data.sources.uspto import UsptoClient

    with UsptoClient() as client:
        ok, message = client.probe()
        return UsptoProbeResponse(ok=ok, message=message)


@router.post("/ingest/patents", response_model=TaskAccepted, status_code=202)
def uspto_ingest_patents(req: UsptoPatentIngestRequest) -> TaskAccepted:
    task = ingest_uspto_patents.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.post("/ingest/trademarks", response_model=TaskAccepted, status_code=202)
def uspto_ingest_trademarks(req: UsptoTrademarkIngestRequest) -> TaskAccepted:
    task = ingest_uspto_trademarks.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.post("/ingest/assignments", response_model=TaskAccepted, status_code=202)
def uspto_ingest_assignments(req: UsptoAssignmentIngestRequest) -> TaskAccepted:
    task = ingest_uspto_assignments.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.get("/patents")
def uspto_patents(
    assignee: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_regulatory import UsptoPatent

    with get_session() as session:
        stmt = select(UsptoPatent)
        if assignee:
            stmt = stmt.where(UsptoPatent.assignee == assignee)
        stmt = stmt.order_by(desc(UsptoPatent.grant_date)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "patent_number": r.patent_number,
            "title": r.title,
            "assignee": r.assignee,
            "grant_date": str(r.grant_date) if r.grant_date else None,
            "filing_date": str(r.filing_date) if r.filing_date else None,
            "classification": r.classification,
        }
        for r in rows
    ]


@router.get("/trademarks")
def uspto_trademarks(
    owner: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_regulatory import UsptoTrademark

    with get_session() as session:
        stmt = select(UsptoTrademark)
        if owner:
            stmt = stmt.where(UsptoTrademark.owner == owner)
        stmt = stmt.order_by(desc(UsptoTrademark.filing_date)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "serial_number": r.serial_number,
            "registration_number": r.registration_number,
            "mark_text": r.mark_text,
            "owner": r.owner,
            "status": r.status,
            "filing_date": str(r.filing_date) if r.filing_date else None,
        }
        for r in rows
    ]


@router.get("/assignments")
def uspto_assignments(
    assignee: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_regulatory import UsptoAssignment

    with get_session() as session:
        stmt = select(UsptoAssignment)
        if assignee:
            stmt = stmt.where(UsptoAssignment.assignee == assignee)
        stmt = stmt.order_by(desc(UsptoAssignment.recorded_date)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "assignment_id": r.assignment_id,
            "assignor": r.assignor,
            "assignee": r.assignee,
            "patents": r.patents,
            "recorded_date": str(r.recorded_date) if r.recorded_date else None,
            "execution_date": str(r.execution_date) if r.execution_date else None,
        }
        for r in rows
    ]
