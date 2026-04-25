"""REST endpoints for FRED (Federal Reserve Economic Data).

Mirrors the subset of the FRED API we care about and ties it into the
shared ingestion / lineage plumbing. All endpoints are safe to call
without a key as long as either (a) the ``AQP_FRED_API_KEY`` env var is
set, or (b) the route allows the ``FredClientError`` to flow back to
the caller as a 503.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from aqp.api.schemas import TaskAccepted
from aqp.persistence.db import get_session
from aqp.persistence.models import FredSeries
from aqp.tasks.ingestion_tasks import ingest_fred_series

router = APIRouter(prefix="/fred", tags=["fred"])


class FredSeriesSummary(BaseModel):
    series_id: str
    title: str
    units: str | None = None
    units_short: str | None = None
    frequency: str | None = None
    frequency_short: str | None = None
    seasonal_adjustment_short: str | None = None
    popularity: int | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    last_updated: datetime | None = None


class FredSearchResponse(BaseModel):
    query: str
    count: int
    results: list[FredSeriesSummary] = Field(default_factory=list)


class FredSeriesDetail(FredSeriesSummary):
    notes: str | None = None
    realtime_start: str | None = None
    realtime_end: str | None = None


class FredIngestRequest(BaseModel):
    series_ids: list[str] = Field(..., min_length=1, description="FRED series ids, e.g. ['DGS10', 'UNRATE']")
    start: str | None = Field(default=None, description="observation_start (YYYY-MM-DD)")
    end: str | None = Field(default=None, description="observation_end (YYYY-MM-DD)")
    units: str | None = Field(default=None, description="FRED unit transform override")
    frequency: str | None = Field(default=None, description="FRED aggregation frequency override")


class FredObservation(BaseModel):
    observation_date: datetime
    value: float | None = None
    realtime_start: datetime | None = None
    realtime_end: datetime | None = None


class FredObservationsResponse(BaseModel):
    series_id: str
    count: int
    observations: list[FredObservation] = Field(default_factory=list)


def _client():
    from aqp.data.sources.fred.client import FredClient

    return FredClient()


def _adapter():
    from aqp.data.sources.fred.series import FredSeriesAdapter

    return FredSeriesAdapter()


@router.get("/probe")
def fred_probe() -> dict[str, Any]:
    """Cheap health check — confirms the FRED key is set and the API is reachable."""
    ok, message = _client().probe()
    return {"ok": bool(ok), "message": message}


@router.get("/series/search", response_model=FredSearchResponse)
def fred_search(
    q: str = Query(..., min_length=2, description="Search text"),
    limit: int = Query(default=25, ge=1, le=100),
) -> FredSearchResponse:
    try:
        hits = _client().search_series(q, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    results = [
        FredSeriesSummary(
            series_id=str(hit.get("id") or ""),
            title=str(hit.get("title") or ""),
            units=hit.get("units"),
            units_short=hit.get("units_short"),
            frequency=hit.get("frequency"),
            frequency_short=hit.get("frequency_short"),
            seasonal_adjustment_short=hit.get("seasonal_adjustment_short"),
            popularity=hit.get("popularity"),
            observation_start=hit.get("observation_start"),
            observation_end=hit.get("observation_end"),
            last_updated=_parse_dt(hit.get("last_updated")),
        )
        for hit in hits
    ]
    return FredSearchResponse(query=q, count=len(results), results=results)


@router.get("/series/{series_id}", response_model=FredSeriesDetail)
def fred_series_detail(series_id: str) -> FredSeriesDetail:
    try:
        record = _client().get_series(series_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail=f"series {series_id} not found")
    return FredSeriesDetail(
        series_id=str(record.get("id") or series_id),
        title=str(record.get("title") or ""),
        units=record.get("units"),
        units_short=record.get("units_short"),
        frequency=record.get("frequency"),
        frequency_short=record.get("frequency_short"),
        seasonal_adjustment_short=record.get("seasonal_adjustment_short"),
        popularity=record.get("popularity"),
        observation_start=record.get("observation_start"),
        observation_end=record.get("observation_end"),
        last_updated=_parse_dt(record.get("last_updated")),
        notes=record.get("notes"),
        realtime_start=record.get("realtime_start"),
        realtime_end=record.get("realtime_end"),
    )


@router.get("/series/{series_id}/observations", response_model=FredObservationsResponse)
def fred_observations(
    series_id: str,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=5000, ge=10, le=200000),
    persist: bool = Query(default=False, description="Persist to parquet lake"),
) -> FredObservationsResponse:
    try:
        result = _adapter().fetch_observations(
            series_id=series_id,
            start=start,
            end=end,
            persist=persist,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    df = result.data.tail(limit).copy()
    observations = [
        FredObservation(
            observation_date=row["observation_date"],
            value=float(row["value"]) if row.get("value") is not None else None,
            realtime_start=row.get("realtime_start"),
            realtime_end=row.get("realtime_end"),
        )
        for row in df.to_dict(orient="records")
    ]
    return FredObservationsResponse(
        series_id=series_id,
        count=len(observations),
        observations=observations,
    )


@router.post("/ingest", response_model=TaskAccepted)
def fred_ingest(req: FredIngestRequest) -> TaskAccepted:
    async_result = ingest_fred_series.delay(
        req.series_ids,
        req.start,
        req.end,
        req.units,
        req.frequency,
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.get("/catalog", response_model=list[FredSeriesSummary])
def fred_catalog(limit: int = Query(default=200, ge=1, le=1000)) -> list[FredSeriesSummary]:
    """Return the locally-cached FRED series catalog."""
    with get_session() as session:
        rows = session.execute(
            select(FredSeries).order_by(desc(FredSeries.updated_at)).limit(limit)
        ).scalars().all()
        return [
            FredSeriesSummary(
                series_id=row.series_id,
                title=row.title or "",
                units=row.units,
                units_short=row.units_short,
                frequency=row.frequency,
                frequency_short=row.frequency_short,
                seasonal_adjustment_short=row.seasonal_adj_short,
                popularity=row.popularity,
                observation_start=row.observation_start.isoformat() if row.observation_start else None,
                observation_end=row.observation_end.isoformat() if row.observation_end else None,
                last_updated=row.last_updated,
            )
            for row in rows
        ]


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        try:
            import pandas as pd

            ts = pd.Timestamp(value)
            return None if ts is pd.NaT else ts.to_pydatetime()
        except Exception:
            return None
