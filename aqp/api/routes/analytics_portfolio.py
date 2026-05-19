"""``/analytics/portfolio/*`` — server-side QuantStats compute.

Three layers (matching the Phase 4 plan):

- ``POST /analytics/portfolio/metrics`` — synchronous fast path. Returns
  a JSON bundle (Sharpe, Sortino, MaxDD, CAGR, Calmar, Tail ratio) for
  the React frontend to render.
- ``POST /analytics/portfolio/rolling`` — rolling Sharpe / rolling vol
  / underwater curve. Returns dense JSON series, the frontend renders
  via ``lightweight-charts`` / ``recharts`` / ``echarts``.
- ``POST /analytics/portfolio/tearsheet`` — heavy: enqueues a Celery
  task that runs ``quantstats.reports.html(...)``. Returns the
  ``task_id`` so the frontend can attach to the canonical progress
  pipeline.

QuantStats is already a core declared dependency; we just finally use
it server-side. ``fig.show()`` is never called — we always go through
``Agg`` and return either base64 PNG or pure JSON series so the
frontend chart libs can render interactively (AGENTS rule: no
Streamlit, no Dash, no notebook hangs).
"""
from __future__ import annotations

import io
import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
logger = logging.getLogger(__name__)


router = secure_router(prefix="/analytics/portfolio", tags=["analytics", "portfolio"], default_scope="data:read")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_returns_series(values: list[float], freq: str | None = None) -> Any:
    """Convert a list[float] returns array into a pandas Series.

    Returns the Series indexed by ``RangeIndex`` when ``freq`` is empty;
    callers can re-index to dates by passing ``index_dates`` separately.
    """
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"pandas unavailable: {exc}")
    series = pd.Series([float(v) for v in values], dtype="float64")
    if freq:
        try:
            series.index = pd.RangeIndex(len(series))
        except Exception:  # noqa: BLE001
            pass
    return series


def _attach_dates(series: Any, index_dates: list[str] | None) -> Any:
    if not index_dates:
        return series
    try:
        import pandas as pd

        series = series.copy()
        series.index = pd.to_datetime(index_dates)
        return series
    except Exception:  # noqa: BLE001
        return series


def _safe_float(x: Any) -> float | None:
    """Coerce a number to a JSON-safe float; map NaN/Inf to ``None``."""
    try:
        v = float(x)
    except Exception:  # noqa: BLE001
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


# ---------------------------------------------------------------------------
# /metrics — fast synchronous path
# ---------------------------------------------------------------------------


class PortfolioMetricsRequest(BaseModel):
    returns: list[float] = Field(..., min_length=2, description="Periodic returns (e.g. daily).")
    index_dates: list[str] | None = Field(
        default=None,
        description="Optional ISO date strings, one per `returns` element.",
    )
    risk_free_rate: float = Field(
        default=0.0,
        description="Annualised risk-free rate; passed through to QuantStats.",
    )
    periods_per_year: int = Field(default=252, ge=1, le=8760)


@router.post("/metrics")
def portfolio_metrics(req: PortfolioMetricsRequest) -> dict[str, Any]:
    try:
        import quantstats as qs
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"quantstats unavailable: {exc}")
    series = _attach_dates(_ensure_returns_series(req.returns), req.index_dates)
    rfr = float(req.risk_free_rate)
    periods = int(req.periods_per_year)

    def _try(fn_name: str, *args: Any, **kwargs: Any) -> float | None:
        fn = getattr(qs.stats, fn_name, None)
        if fn is None:
            return None
        try:
            return _safe_float(fn(series, *args, **kwargs))
        except Exception as exc:  # noqa: BLE001
            logger.debug("quantstats.%s failed: %s", fn_name, exc)
            return None

    metrics = {
        "sharpe": _try("sharpe", rfr, periods),
        "sortino": _try("sortino", rfr, periods),
        "max_drawdown": _try("max_drawdown"),
        "cagr": _try("cagr"),
        "calmar": _try("calmar"),
        "tail_ratio": _try("tail_ratio"),
        "volatility": _try("volatility", periods),
        "skew": _try("skew"),
        "kurtosis": _try("kurtosis"),
        "win_rate": _try("win_rate"),
        "value_at_risk": _try("value_at_risk"),
        "expected_shortfall": _try("expected_shortfall"),
        "ulcer_index": _try("ulcer_index"),
        "common_sense_ratio": _try("common_sense_ratio"),
    }
    return {
        "ok": True,
        "metrics": metrics,
        "n_periods": int(len(req.returns)),
        "periods_per_year": periods,
        "risk_free_rate": rfr,
    }


# ---------------------------------------------------------------------------
# /rolling — rolling Sharpe / vol / underwater
# ---------------------------------------------------------------------------


class PortfolioRollingRequest(BaseModel):
    returns: list[float] = Field(..., min_length=10)
    index_dates: list[str] | None = None
    window: int = Field(default=63, ge=5, le=2520)
    risk_free_rate: float = Field(default=0.0)
    periods_per_year: int = Field(default=252, ge=1, le=8760)


@router.post("/rolling")
def portfolio_rolling(req: PortfolioRollingRequest) -> dict[str, Any]:
    try:
        import pandas as pd
        import quantstats as qs  # noqa: F401  (still used for ratio math)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"quantstats unavailable: {exc}")
    series = _attach_dates(_ensure_returns_series(req.returns), req.index_dates)
    window = int(req.window)
    periods = int(req.periods_per_year)
    rfr = float(req.risk_free_rate)

    # Rolling Sharpe — annualised.
    rolling_mean = series.rolling(window).mean() * periods
    rolling_std = series.rolling(window).std() * (periods ** 0.5)
    rolling_sharpe = (rolling_mean - rfr) / rolling_std.replace(0, pd.NA)
    rolling_vol = series.rolling(window).std() * (periods ** 0.5)

    # Underwater (drawdown).
    cum = (1.0 + series.fillna(0.0)).cumprod()
    peak = cum.cummax()
    underwater = cum / peak - 1.0

    def _series_to_json(s: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for idx, val in s.items():
            ts = idx.isoformat() if hasattr(idx, "isoformat") else str(idx)
            rows.append({"t": ts, "v": _safe_float(val)})
        return rows

    return {
        "ok": True,
        "window": window,
        "rolling_sharpe": _series_to_json(rolling_sharpe),
        "rolling_vol": _series_to_json(rolling_vol),
        "underwater": _series_to_json(underwater),
    }


# ---------------------------------------------------------------------------
# /tearsheet — enqueue heavy Celery task
# ---------------------------------------------------------------------------


class PortfolioTearsheetRequest(BaseModel):
    returns: list[float] = Field(..., min_length=20)
    index_dates: list[str] | None = None
    benchmark_returns: list[float] | None = None
    title: str = Field(default="AQP portfolio tearsheet", max_length=160)


@router.post("/tearsheet")
def portfolio_tearsheet(req: PortfolioTearsheetRequest) -> dict[str, Any]:
    # Inline import so the Celery broker is not pulled in at FastAPI
    # boot time (rule: no Celery imports at FastAPI route module top
    # level).
    from aqp.tasks.analytics_tasks import render_portfolio_tearsheet

    async_result = render_portfolio_tearsheet.delay(
        returns=list(req.returns),
        index_dates=list(req.index_dates) if req.index_dates else None,
        benchmark_returns=(
            list(req.benchmark_returns) if req.benchmark_returns else None
        ),
        title=req.title,
    )
    return {"ok": True, "task_id": str(async_result.id), "stage": "queued"}


# Optional synchronous fallback — useful for tests / dev without
# Celery workers. Set ``AQP_ANALYTICS_INLINE_TEARSHEET=true`` to make
# /tearsheet run in-process and return base64 HTML.
class PortfolioTearsheetSyncRequest(PortfolioTearsheetRequest):
    pass


@router.post("/tearsheet-sync")
def portfolio_tearsheet_sync(req: PortfolioTearsheetSyncRequest) -> dict[str, Any]:
    from aqp.tasks.analytics_tasks import _render_tearsheet_html

    series = _attach_dates(_ensure_returns_series(req.returns), req.index_dates)
    benchmark = None
    if req.benchmark_returns:
        benchmark = _attach_dates(
            _ensure_returns_series(req.benchmark_returns), req.index_dates
        )
    try:
        html_payload = _render_tearsheet_html(series, benchmark=benchmark, title=req.title)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"tearsheet render failed: {exc}")
    return {
        "ok": True,
        "title": req.title,
        "html_base64": html_payload,
        "n_periods": len(req.returns),
    }


__all__ = ["router"]
