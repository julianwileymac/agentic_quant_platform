"""Feature-Set CRUD + preview + materialise + usages.

A :class:`FeatureSet` is a named, versioned bundle of indicator /
model-prediction specs consumed identically by backtests, training,
live trading, and RL.

Endpoints
---------

- ``GET    /feature-sets`` — list active feature sets (filterable).
- ``POST   /feature-sets`` — create.
- ``GET    /feature-sets/{id}`` — detail.
- ``PUT    /feature-sets/{id}`` — update; auto-bumps version when specs change.
- ``DELETE /feature-sets/{id}`` — soft-delete (status = archived).
- ``GET    /feature-sets/{id}/versions`` — version history.
- ``POST   /feature-sets/{id}/preview`` — synchronous small-scale materialisation.
- ``POST   /feature-sets/{id}/materialize`` — Celery task.
- ``GET    /feature-sets/{id}/usages`` — lineage rows.
- ``POST   /feature-sets/preview-specs`` — ad-hoc materialisation without persistence.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted
from aqp.core.types import Symbol
from aqp.data.feature_sets import (
    FeatureSetService,
    FeatureSetSpec,
    FeatureSetSummary,
    FeatureSetUsageRow,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feature-sets", tags=["feature-sets"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FeatureSetCreate(BaseModel):
    name: str
    description: str | None = None
    kind: str = "indicator"
    specs: list[str] = Field(default_factory=list)
    default_lookback_days: int = 60
    tags: list[str] = Field(default_factory=list)
    created_by: str | None = None


class FeatureSetUpdate(BaseModel):
    description: str | None = None
    kind: str = "indicator"
    specs: list[str] = Field(default_factory=list)
    default_lookback_days: int = 60
    tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    created_by: str | None = None


class FeatureSetPreview(BaseModel):
    symbols: list[str]
    start: str
    end: str
    rows: int = Field(default=50, ge=1, le=2000)


class AdHocPreview(BaseModel):
    specs: list[str]
    symbols: list[str]
    start: str
    end: str
    rows: int = Field(default=50, ge=1, le=2000)


class MaterializeRequest(BaseModel):
    symbols: list[str]
    start: str
    end: str
    consumer_kind: str = "research"
    consumer_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service() -> FeatureSetService:
    return FeatureSetService()


def _load_bars(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    provider = DuckDBHistoryProvider()
    return provider.get_bars(
        [Symbol.parse(s) for s in symbols],
        start=pd.Timestamp(start),
        end=pd.Timestamp(end),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=list[FeatureSetSummary])
def list_feature_sets(
    limit: int = 100,
    kind: str | None = None,
) -> list[FeatureSetSummary]:
    return _service().list(limit=limit, kind=kind)


@router.post("", response_model=FeatureSetSummary)
def create_feature_set(req: FeatureSetCreate) -> FeatureSetSummary:
    spec = FeatureSetSpec(
        name=req.name,
        description=req.description,
        kind=req.kind,
        specs=req.specs,
        default_lookback_days=req.default_lookback_days,
        tags=req.tags,
    )
    try:
        return _service().create(spec, created_by=req.created_by)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{feature_set_id}", response_model=FeatureSetSummary)
def get_feature_set(feature_set_id: str) -> FeatureSetSummary:
    summary = _service().get(feature_set_id)
    if summary is None:
        raise HTTPException(404, f"no feature set {feature_set_id!r}")
    return summary


@router.put("/{feature_set_id}", response_model=FeatureSetSummary)
def update_feature_set(
    feature_set_id: str,
    req: FeatureSetUpdate,
) -> FeatureSetSummary:
    spec = FeatureSetSpec(
        name="",  # ignored
        description=req.description,
        kind=req.kind,
        specs=req.specs,
        default_lookback_days=req.default_lookback_days,
        tags=req.tags,
    )
    try:
        return _service().update(
            feature_set_id,
            spec,
            notes=req.notes,
            created_by=req.created_by,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/{feature_set_id}")
def delete_feature_set(feature_set_id: str) -> dict[str, Any]:
    _service().delete(feature_set_id)
    return {"status": "archived", "feature_set_id": feature_set_id}


@router.get("/{feature_set_id}/versions")
def list_versions(feature_set_id: str) -> list[dict[str, Any]]:
    return _service().versions(feature_set_id)


@router.post("/{feature_set_id}/preview")
def preview_feature_set(
    feature_set_id: str,
    req: FeatureSetPreview,
) -> dict[str, Any]:
    summary = _service().get(feature_set_id)
    if summary is None:
        raise HTTPException(404, f"no feature set {feature_set_id!r}")
    bars = _load_bars(req.symbols, req.start, req.end)
    if bars.empty:
        return {
            "feature_set_id": feature_set_id,
            "name": summary.name,
            "columns": [],
            "rows": [],
            "n_rows": 0,
            "warning": "no bars for requested range",
        }
    panel = _service().materialize(feature_set_id, bars, use_cache=False)
    tail = panel.tail(int(req.rows)).fillna(value=0)
    cols = [c for c in tail.columns if c not in ("timestamp", "vt_symbol")]
    return {
        "feature_set_id": feature_set_id,
        "name": summary.name,
        "version": summary.version,
        "columns": list(tail.columns),
        "feature_columns": cols,
        "rows": tail.astype(object).where(tail.notna(), None).to_dict(orient="records"),
        "n_rows": int(len(panel)),
    }


@router.post("/preview-specs")
def preview_ad_hoc(req: AdHocPreview) -> dict[str, Any]:
    bars = _load_bars(req.symbols, req.start, req.end)
    if bars.empty:
        return {
            "specs": req.specs,
            "columns": [],
            "rows": [],
            "n_rows": 0,
            "warning": "no bars for requested range",
        }
    panel = _service().materialize_ad_hoc(req.specs, bars)
    tail = panel.tail(int(req.rows)).fillna(value=0)
    return {
        "specs": req.specs,
        "columns": list(tail.columns),
        "rows": tail.astype(object).where(tail.notna(), None).to_dict(orient="records"),
        "n_rows": int(len(panel)),
    }


@router.post("/{feature_set_id}/materialize", response_model=TaskAccepted)
def materialize_feature_set(
    feature_set_id: str,
    req: MaterializeRequest,
) -> TaskAccepted:
    from aqp.tasks.feature_set_tasks import materialize_feature_set as task

    summary = _service().get(feature_set_id)
    if summary is None:
        raise HTTPException(404, f"no feature set {feature_set_id!r}")
    async_result = task.delay(
        feature_set_id,
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        consumer_kind=req.consumer_kind,
        consumer_id=req.consumer_id,
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/{feature_set_id}/usages", response_model=list[FeatureSetUsageRow])
def list_usages(feature_set_id: str, limit: int = 100) -> list[FeatureSetUsageRow]:
    return _service().usages(feature_set_id, limit=limit)
