"""REST endpoints for SEC EDGAR filings."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import SecFiling
from aqp.tasks.ingestion_tasks import ingest_sec_filings

router = APIRouter(prefix="/sec", tags=["sec"])


class SecFilingSummary(BaseModel):
    accession_no: str
    cik: str
    form: str
    filed_at: datetime | None = None
    period_of_report: datetime | None = None
    primary_doc_url: str | None = None
    primary_doc_type: str | None = None
    xbrl_available: bool = False
    items: list[str] = Field(default_factory=list)


class SecFilingsResponse(BaseModel):
    cik_or_ticker: str
    count: int
    filings: list[SecFilingSummary] = Field(default_factory=list)


class SecIngestRequest(BaseModel):
    cik_or_ticker: str = Field(..., description="CIK or ticker symbol")
    form: str | list[str] | None = Field(default=None, description="Single form or list")
    start: str | None = None
    end: str | None = None
    artifacts: list[str] = Field(
        default_factory=list,
        description="Parsed artifacts: financials | insider | holdings",
    )
    limit: int | None = 100


class SecFinancialsRow(BaseModel):
    concept: str
    statement: str
    period: str
    value: float | None = None
    cik: str | None = None
    ticker: str | None = None


class SecFinancialsResponse(BaseModel):
    cik_or_ticker: str
    count: int
    rows: list[SecFinancialsRow] = Field(default_factory=list)


def _client():
    from aqp.data.sources.sec.client import SecClient

    return SecClient()


def _adapter():
    from aqp.data.sources.sec.filings import SecFilingsAdapter

    return SecFilingsAdapter()


@router.get("/probe")
def sec_probe() -> dict[str, Any]:
    """Cheap health check — confirms the edgartools identity is configured."""
    ok, message = _client().probe()
    return {"ok": bool(ok), "message": message}


@router.get("/company/{cik_or_ticker}/filings", response_model=SecFilingsResponse)
def sec_company_filings(
    cik_or_ticker: str,
    form: str | None = Query(default=None),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=200),
) -> SecFilingsResponse:
    try:
        payload = _adapter().fetch_metadata(
            cik_or_ticker=cik_or_ticker,
            form=form,
            start=start,
            end=end,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    filings = [
        SecFilingSummary(
            accession_no=str(row.get("accession_no") or ""),
            cik=str(row.get("cik") or ""),
            form=str(row.get("form") or ""),
            filed_at=_to_dt(row.get("filed_at")),
            period_of_report=_to_dt(row.get("period_of_report")),
            primary_doc_url=row.get("primary_doc_url"),
            primary_doc_type=row.get("primary_doc_type"),
            xbrl_available=bool(row.get("xbrl_available")),
            items=[str(i) for i in (row.get("items") or [])],
        )
        for row in payload.get("filings", [])
    ]
    return SecFilingsResponse(
        cik_or_ticker=cik_or_ticker,
        count=len(filings),
        filings=filings,
    )


@router.get(
    "/company/{cik_or_ticker}/financials", response_model=SecFinancialsResponse
)
def sec_financials(
    cik_or_ticker: str,
    persist: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=5000),
) -> SecFinancialsResponse:
    try:
        result = _adapter().fetch_observations(
            cik_or_ticker=cik_or_ticker,
            artifact="financials",
            persist=persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.data is None or result.data.empty:
        return SecFinancialsResponse(cik_or_ticker=cik_or_ticker, count=0)
    df = result.data.tail(limit)
    rows = [
        SecFinancialsRow(
            concept=str(record.get("concept") or ""),
            statement=str(record.get("statement") or ""),
            period=str(record.get("period") or ""),
            value=_maybe_float(record.get("value")),
            cik=str(record.get("cik")) if record.get("cik") else None,
            ticker=record.get("ticker"),
        )
        for record in df.to_dict(orient="records")
    ]
    return SecFinancialsResponse(
        cik_or_ticker=cik_or_ticker,
        count=len(rows),
        rows=rows,
    )


@router.get("/company/{cik_or_ticker}/insider")
def sec_insider(
    cik_or_ticker: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    persist: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=2000),
) -> dict[str, Any]:
    try:
        result = _adapter().fetch_observations(
            cik_or_ticker=cik_or_ticker,
            artifact="insider",
            start=start,
            end=end,
            persist=persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.data is None or result.data.empty:
        return {"cik_or_ticker": cik_or_ticker, "count": 0, "transactions": []}
    df = result.data.tail(limit).copy()
    df = df.astype(object).where(df.notna(), None)
    return {
        "cik_or_ticker": cik_or_ticker,
        "count": int(len(df)),
        "transactions": df.to_dict(orient="records"),
    }


@router.get("/company/{cik_or_ticker}/holdings")
def sec_holdings(
    cik_or_ticker: str,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    persist: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        result = _adapter().fetch_observations(
            cik_or_ticker=cik_or_ticker,
            artifact="holdings",
            start=start,
            end=end,
            persist=persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if result.data is None or result.data.empty:
        return {"cik_or_ticker": cik_or_ticker, "count": 0, "holdings": []}
    df = result.data.tail(limit).copy()
    df = df.astype(object).where(df.notna(), None)
    return {
        "cik_or_ticker": cik_or_ticker,
        "count": int(len(df)),
        "holdings": df.to_dict(orient="records"),
    }


@router.post("/ingest", response_model=TaskAccepted)
def sec_ingest(req: SecIngestRequest) -> TaskAccepted:
    async_result = ingest_sec_filings.delay(
        req.cik_or_ticker,
        req.form,
        req.start,
        req.end,
        req.artifacts,
        req.limit,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/filings/recent", response_model=list[SecFilingSummary])
def sec_recent(
    limit: int = Query(default=100, ge=1, le=1000),
    form: str | None = Query(default=None),
) -> list[SecFilingSummary]:
    """Return the most recent filings indexed locally."""
    with get_session() as session:
        stmt = select(SecFiling).order_by(desc(SecFiling.filed_at))
        if form:
            stmt = stmt.where(SecFiling.form == form)
        rows = session.execute(stmt.limit(limit)).scalars().all()
        return [
            SecFilingSummary(
                accession_no=row.accession_no,
                cik=row.cik,
                form=row.form,
                filed_at=row.filed_at,
                period_of_report=row.period_of_report,
                primary_doc_url=row.primary_doc_url,
                primary_doc_type=row.primary_doc_type,
                xbrl_available=bool(row.xbrl_available),
                items=[str(i) for i in (row.items or [])],
            )
            for row in rows
        ]


def _to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        import pandas as pd

        ts = pd.Timestamp(value)
        return None if ts is pd.NaT else ts.to_pydatetime()
    except Exception:
        return None


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
