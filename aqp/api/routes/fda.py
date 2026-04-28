"""REST endpoints for the FDA openFDA adapter."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.tasks.regulatory_tasks import (
    ingest_fda_adverse_events,
    ingest_fda_applications,
    ingest_fda_recalls,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fda", tags=["fda", "regulatory"])


class FdaProbeResponse(BaseModel):
    ok: bool
    message: str


class FdaApplicationIngestRequest(BaseModel):
    sponsor: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    endpoint: str = Field(default="drug/drugsfda.json")
    max_records: int | None = Field(default=5000, ge=1, le=50_000)
    vt_symbol: str | None = None


class FdaAdverseEventIngestRequest(BaseModel):
    manufacturer: str | None = None
    product: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    endpoint: str = Field(default="drug/event.json")
    max_records: int | None = Field(default=5000, ge=1, le=50_000)
    vt_symbol: str | None = None


class FdaRecallIngestRequest(BaseModel):
    firm: str | None = None
    classification: str | None = None
    date_min: str | None = None
    date_max: str | None = None
    product_type: str = Field(default="drug")
    max_records: int | None = Field(default=5000, ge=1, le=50_000)
    vt_symbol: str | None = None


@router.get("/probe", response_model=FdaProbeResponse)
def fda_probe() -> FdaProbeResponse:
    from aqp.data.sources.fda import FdaClient

    with FdaClient() as client:
        ok, message = client.probe()
        return FdaProbeResponse(ok=ok, message=message)


@router.get("/search/{endpoint:path}")
def fda_search(
    endpoint: str,
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    from aqp.data.sources.fda import FdaClient

    with FdaClient() as client:
        try:
            page = client.search(endpoint, search=search, limit=limit)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"count": len(page.get("results") or []), "results": page.get("results") or []}


@router.post("/ingest/applications", response_model=TaskAccepted, status_code=202)
def fda_ingest_applications(req: FdaApplicationIngestRequest) -> TaskAccepted:
    task = ingest_fda_applications.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.post("/ingest/adverse-events", response_model=TaskAccepted, status_code=202)
def fda_ingest_adverse(req: FdaAdverseEventIngestRequest) -> TaskAccepted:
    task = ingest_fda_adverse_events.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.post("/ingest/recalls", response_model=TaskAccepted, status_code=202)
def fda_ingest_recalls(req: FdaRecallIngestRequest) -> TaskAccepted:
    task = ingest_fda_recalls.delay(**req.model_dump())
    return TaskAccepted(task_id=task.id, stream_url=f"/ws/progress/{task.id}")


@router.get("/applications")
def fda_applications(
    sponsor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_regulatory import FdaApplication

    with get_session() as session:
        stmt = select(FdaApplication)
        if sponsor:
            stmt = stmt.where(FdaApplication.sponsor_name == sponsor)
        stmt = stmt.order_by(desc(FdaApplication.submission_date)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "application_number": r.application_number,
            "application_type": r.application_type,
            "sponsor_name": r.sponsor_name,
            "drug_name": r.drug_name,
            "submission_date": str(r.submission_date) if r.submission_date else None,
            "submission_status": r.submission_status,
        }
        for r in rows
    ]


@router.get("/recalls")
def fda_recalls(
    firm: str | None = Query(default=None),
    classification: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from aqp.persistence.models_regulatory import FdaRecall

    with get_session() as session:
        stmt = select(FdaRecall)
        if firm:
            stmt = stmt.where(FdaRecall.recalling_firm == firm)
        if classification:
            stmt = stmt.where(FdaRecall.classification == classification)
        stmt = stmt.order_by(desc(FdaRecall.recall_initiation_date)).limit(limit)
        rows = session.execute(stmt).scalars().all()
    return [
        {
            "recall_number": r.recall_number,
            "recalling_firm": r.recalling_firm,
            "classification": r.classification,
            "status": r.status,
            "product_description": r.product_description,
            "recall_initiation_date": str(r.recall_initiation_date) if r.recall_initiation_date else None,
        }
        for r in rows
    ]
