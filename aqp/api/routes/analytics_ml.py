"""``/analytics/ml/*`` — visualisation payloads for ML test outputs.

Reads the existing ``ml_test_tasks`` outputs (distribution overlays,
drift heatmaps, perturbation sweeps) and shapes them into JSON the
Vite frontend renders via ``recharts`` (bar/area), ``lightweight-charts``
(time series), and ``echarts`` (heatmaps).

The routes are intentionally thin — they don't compute anything heavy.
Heavy work stays on the existing Celery task pipeline and emits
progress via the canonical frame (AGENTS rule 4).
"""
from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/analytics/ml", tags=["analytics", "ml"])


def _safe_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:  # noqa: BLE001
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


class DistributionRequest(BaseModel):
    actual: list[float] = Field(..., min_length=2)
    predicted: list[float] = Field(..., min_length=2)
    bins: int = Field(default=30, ge=4, le=200)


@router.post("/distribution-overlay")
def distribution_overlay(req: DistributionRequest) -> dict[str, Any]:
    if len(req.actual) != len(req.predicted):
        raise HTTPException(
            status_code=422,
            detail="actual and predicted must be the same length",
        )
    try:
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"numpy unavailable: {exc}")
    actual = np.asarray(req.actual, dtype=float)
    predicted = np.asarray(req.predicted, dtype=float)
    finite = np.isfinite(actual) & np.isfinite(predicted)
    actual = actual[finite]
    predicted = predicted[finite]
    if actual.size == 0:
        return {"ok": True, "bins": [], "actual": [], "predicted": []}
    lo = float(min(actual.min(), predicted.min()))
    hi = float(max(actual.max(), predicted.max()))
    if lo == hi:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, int(req.bins) + 1)
    actual_hist, _ = np.histogram(actual, bins=edges)
    predicted_hist, _ = np.histogram(predicted, bins=edges)
    centers = 0.5 * (edges[:-1] + edges[1:])
    return {
        "ok": True,
        "bins": [_safe_float(c) for c in centers.tolist()],
        "actual": [int(x) for x in actual_hist.tolist()],
        "predicted": [int(x) for x in predicted_hist.tolist()],
        "n_actual": int(actual.size),
        "n_predicted": int(predicted.size),
    }


class DriftHeatmapRequest(BaseModel):
    matrix: list[list[float]] = Field(..., description="2D matrix of drift values.")
    x_labels: list[str] = Field(default_factory=list)
    y_labels: list[str] = Field(default_factory=list)


@router.post("/drift-heatmap")
def drift_heatmap(req: DriftHeatmapRequest) -> dict[str, Any]:
    if not req.matrix:
        return {"ok": True, "matrix": [], "x_labels": [], "y_labels": []}
    rows = len(req.matrix)
    cols = len(req.matrix[0]) if rows else 0
    return {
        "ok": True,
        "matrix": [[_safe_float(v) for v in row] for row in req.matrix],
        "x_labels": req.x_labels or [str(i) for i in range(cols)],
        "y_labels": req.y_labels or [str(i) for i in range(rows)],
        "shape": [rows, cols],
    }


class PerturbationSweepRequest(BaseModel):
    feature: str = Field(..., min_length=1)
    grid: list[float]
    metric: str = Field(..., min_length=1)
    values: list[float]


@router.post("/perturbation-sweep")
def perturbation_sweep(req: PerturbationSweepRequest) -> dict[str, Any]:
    if len(req.grid) != len(req.values):
        raise HTTPException(
            status_code=422, detail="grid and values must be the same length"
        )
    return {
        "ok": True,
        "feature": req.feature,
        "metric": req.metric,
        "points": [
            {"x": _safe_float(g), "y": _safe_float(v)}
            for g, v in zip(req.grid, req.values)
        ],
    }


__all__ = ["router"]
