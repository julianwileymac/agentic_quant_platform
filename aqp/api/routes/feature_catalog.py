"""Feature catalog REST endpoints — used by the Feature Set Workbench.

Exposes:

- ``GET /feature-catalog/candidates`` — full list of feed-derived feature
  candidates, filtered by ``source`` / ``domain`` / ``query``.
- ``GET /feature-catalog/sources`` — distinct sources for filtering.
- ``GET /feature-catalog/domains`` — distinct domain paths for filtering.
- ``POST /feature-catalog/preview`` — small materialized sample for one
  candidate so the UI can render an inline chart / coverage bar.
"""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.data.feature_catalog import all_candidates, filter_candidates, to_dicts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feature-catalog", tags=["feature-catalog"])


@router.get("/candidates")
def list_candidates(
    source: str | None = None,
    domain: str | None = None,
    query: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    cands = filter_candidates(
        all_candidates(),
        source=source,
        domain=domain,
        query=query,
    )
    return {
        "candidates": to_dicts(cands[:limit]),
        "total": len(cands),
        "limit": limit,
    }


@router.get("/sources")
def list_sources() -> list[str]:
    return sorted({c.source for c in all_candidates()})


@router.get("/domains")
def list_domains(source: str | None = None) -> list[str]:
    cands = all_candidates()
    if source:
        cands = [c for c in cands if c.source == source]
    return sorted({c.domain for c in cands})


class PreviewRequest(BaseModel):
    candidate_id: str = Field(..., description="e.g. fred.macro.series.DGS10")
    vt_symbol: str | None = Field(default=None, description="for ticker-specific feeds")
    start: str | None = None
    end: str | None = None
    rows: int = Field(default=180, ge=10, le=2000)


@router.post("/preview")
def preview_candidate(req: PreviewRequest) -> dict[str, Any]:
    """Materialize a small sample of a feature candidate for the UI.

    Best-effort: if the underlying provider isn't installed/configured,
    returns ``{ values: [], error: "..." }`` so the UI can show a friendly
    placeholder rather than blowing up.
    """
    cand = next(
        (c for c in all_candidates() if c.id == req.candidate_id),
        None,
    )
    if cand is None:
        raise HTTPException(404, f"unknown candidate: {req.candidate_id}")

    try:
        start_dt = _dt.datetime.fromisoformat(req.start) if req.start else None
    except ValueError:
        start_dt = None
    try:
        end_dt = _dt.datetime.fromisoformat(req.end) if req.end else None
    except ValueError:
        end_dt = None

    values: list[dict[str, Any]] = []
    error: str | None = None

    try:
        if cand.source == "fred":
            values = _preview_fred(cand.field, start=start_dt, end=end_dt, rows=req.rows)
        elif cand.source == "alpha_vantage" and cand.domain == "market.bars":
            values = _preview_av_bars(req.vt_symbol, cand.field, rows=req.rows)
        else:
            error = (
                f"No live preview wired for {cand.source}.{cand.domain}; "
                f"the candidate is still listed for use in feature specs."
            )
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    coverage = _coverage(values) if values else {"non_null": 0, "total": 0, "pct": 0.0}
    return {
        "candidate": {
            "id": cand.id,
            "source": cand.source,
            "domain": cand.domain,
            "field": cand.field,
            "description": cand.description,
        },
        "values": values,
        "count": len(values),
        "coverage": coverage,
        "error": error,
    }


def _coverage(values: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(values)
    non_null = sum(
        1 for v in values if v.get("value") is not None and v.get("value") == v.get("value")
    )
    return {
        "total": total,
        "non_null": non_null,
        "pct": round(non_null / total, 4) if total else 0.0,
    }


def _preview_fred(
    series_id: str,
    *,
    start: _dt.datetime | None,
    end: _dt.datetime | None,
    rows: int,
) -> list[dict[str, Any]]:
    try:
        from aqp.config import settings

        api_key = getattr(settings, "fred_api_key", "") or ""
        if not api_key:
            from fredapi import Fred  # type: ignore[import-not-found]

            client = Fred()
        else:
            from fredapi import Fred  # type: ignore[import-not-found]

            client = Fred(api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"fredapi not available: {exc}") from exc

    series = client.get_series(
        series_id,
        observation_start=start,
        observation_end=end,
    )
    series = series.dropna().tail(rows)
    return [
        {"timestamp": str(idx.date()), "value": float(val)}
        for idx, val in series.items()
    ]


def _preview_av_bars(
    vt_symbol: str | None,
    field: str,
    *,
    rows: int,
) -> list[dict[str, Any]]:
    if not vt_symbol:
        raise RuntimeError("vt_symbol is required for AlphaVantage bar previews")
    from aqp.core.types import DataNormalizationMode, Symbol
    from aqp.data.duckdb_engine import DuckDBHistoryProvider

    sym = Symbol.parse(vt_symbol) if "." in vt_symbol else Symbol(ticker=vt_symbol)
    provider = DuckDBHistoryProvider()
    bars = provider.get_bars_normalized(
        [sym],
        _dt.datetime(2020, 1, 1),
        _dt.datetime.utcnow(),
        interval="1d",
        normalization=DataNormalizationMode.ADJUSTED,
    )
    if bars is None or bars.empty or field not in bars.columns:
        return []
    bars = bars.sort_values("timestamp").tail(rows)
    return [
        {"timestamp": str(row["timestamp"]), "value": _safe_float(row[field])}
        for _, row in bars.iterrows()
    ]


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
        if f != f:
            return None
        return f
    except (TypeError, ValueError):
        return None
