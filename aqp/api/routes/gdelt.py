"""REST endpoints for GDelt GKG 2.0 (hybrid manifest + BigQuery)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import GDeltMention, Instrument
from aqp.tasks.ingestion_tasks import ingest_gdelt_window

router = APIRouter(prefix="/gdelt", tags=["gdelt"])


class ManifestEntryResponse(BaseModel):
    url: str
    size: int
    md5: str
    timestamp: str


class ManifestResponse(BaseModel):
    start: str
    end: str
    count: int
    total_bytes: int
    entries: list[ManifestEntryResponse] = Field(default_factory=list)


class GDeltIngestRequest(BaseModel):
    start: str = Field(..., description="Window start (ISO datetime)")
    end: str = Field(..., description="Window end (ISO datetime)")
    mode: Literal["manifest", "bigquery", "hybrid"] = "manifest"
    tickers: list[str] | None = None
    themes: list[str] | None = None
    subject_filter_only: bool | None = None
    max_files: int | None = Field(default=None, ge=1, le=2000)


class GDeltBigQueryRequest(BaseModel):
    start: str
    end: str
    tickers: list[str] | None = None
    themes: list[str] | None = None
    limit: int = Field(default=10_000, ge=1, le=100_000)


class GDeltMentionResponse(BaseModel):
    gkg_record_id: str
    date: datetime
    source_common_name: str | None = None
    document_identifier: str | None = None
    instrument_id: str | None = None
    themes: list[str] = Field(default_factory=list)
    tone: dict[str, Any] = Field(default_factory=dict)
    organizations_match: list[dict[str, Any]] = Field(default_factory=list)


def _adapter():
    from aqp.data.sources.gdelt.adapter import GDeltAdapter

    return GDeltAdapter()


@router.get("/probe")
def gdelt_probe() -> dict[str, Any]:
    result = _adapter().probe()
    return {
        "ok": bool(result.ok),
        "message": result.message,
        "details": result.details,
    }


@router.get("/manifest", response_model=ManifestResponse)
def gdelt_manifest(
    start: str = Query(..., description="Window start (ISO)"),
    end: str = Query(..., description="Window end (ISO)"),
    force_refresh: bool = Query(default=False),
) -> ManifestResponse:
    try:
        payload = _adapter().fetch_metadata(start=start, end=end, force_refresh=force_refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ManifestResponse(
        start=str(payload.get("start", start)),
        end=str(payload.get("end", end)),
        count=int(payload.get("count", 0)),
        total_bytes=int(payload.get("total_bytes", 0)),
        entries=[
            ManifestEntryResponse(**entry)
            for entry in payload.get("entries", [])
        ],
    )


@router.post("/ingest", response_model=TaskAccepted)
def gdelt_ingest(req: GDeltIngestRequest) -> TaskAccepted:
    async_result = ingest_gdelt_window.delay(
        req.start,
        req.end,
        req.mode,
        req.tickers,
        req.themes,
        req.subject_filter_only,
        req.max_files,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/query")
def gdelt_query(req: GDeltBigQueryRequest) -> dict[str, Any]:
    """Synchronous BigQuery query (requires the ``[gdelt-bq]`` extra)."""
    try:
        result = _adapter().fetch_observations(
            start=req.start,
            end=req.end,
            mode="bigquery",
            tickers=req.tickers,
            themes=req.themes,
            persist=False,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.data is None or result.data.empty:
        return {"count": 0, "rows": []}
    df = result.data.head(req.limit).astype(object)
    df = df.where(df.notna(), None)
    return {"count": int(len(df)), "rows": df.to_dict(orient="records")}


@router.get("/mentions", response_model=list[GDeltMentionResponse])
def gdelt_mentions(
    vt_symbol: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=5000),
) -> list[GDeltMentionResponse]:
    """Return recent GDelt mentions for an instrument (or the whole universe)."""
    with get_session() as session:
        stmt = select(GDeltMention).order_by(desc(GDeltMention.date))
        if vt_symbol or ticker:
            inst = session.execute(
                select(Instrument).where(
                    (Instrument.vt_symbol == vt_symbol)
                    | (Instrument.ticker == (ticker or "").upper())
                ).limit(1)
            ).scalar_one_or_none()
            if inst is None:
                return []
            stmt = stmt.where(GDeltMention.instrument_id == inst.id)
        if start:
            stmt = stmt.where(GDeltMention.date >= datetime.fromisoformat(start))
        if end:
            stmt = stmt.where(GDeltMention.date <= datetime.fromisoformat(end))
        rows = session.execute(stmt.limit(limit)).scalars().all()
        return [
            GDeltMentionResponse(
                gkg_record_id=row.gkg_record_id,
                date=row.date,
                source_common_name=row.source_common_name,
                document_identifier=row.document_identifier,
                instrument_id=row.instrument_id,
                themes=list(row.themes or []),
                tone=dict(row.tone or {}),
                organizations_match=list(row.organizations_match or []),
            )
            for row in rows
        ]
