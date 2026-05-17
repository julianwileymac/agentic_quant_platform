"""Celery tasks backing the Phase 4 ``/analytics/*`` routes.

Heavy work — ``quantstats.reports.html`` (a multi-second matplotlib
render), pandas-ta indicator runs, and any future portfolio rollup
that exceeds the FastAPI request budget — runs here so the API stays
responsive. Progress is published via the canonical
:func:`emit / emit_done / emit_error` (AGENTS rule 4); the frontend
attaches via the existing ``useLiveStream`` pipeline.
"""
from __future__ import annotations

import base64
import io
import logging
import math
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _safe_float(x: Any) -> float | None:
    try:
        v = float(x)
    except Exception:  # noqa: BLE001
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def _build_series(
    values: list[float], index_dates: list[str] | None = None
) -> Any:
    import pandas as pd

    s = pd.Series([float(v) for v in values], dtype="float64")
    if index_dates:
        try:
            s.index = pd.to_datetime(index_dates)
        except Exception:  # noqa: BLE001
            pass
    return s


def _render_tearsheet_html(series: Any, *, benchmark: Any = None, title: str = "AQP tearsheet") -> str:
    """Render a quantstats HTML tearsheet and return it base64-encoded.

    The base64 envelope keeps the JSON payload uniform; the frontend
    decodes it client-side and stuffs it into an ``<iframe srcdoc>``
    so the agent does not have to follow another URL.

    The ``Agg`` matplotlib backend is set explicitly — never
    ``fig.show()`` — so the task runs cleanly inside a Celery worker
    with no display attached.
    """
    import matplotlib

    matplotlib.use("Agg")
    import quantstats as qs

    buf = io.BytesIO()
    # quantstats writes HTML directly to a path or buffer; some
    # versions only accept a file path so we tee through a tempfile.
    try:
        qs.reports.html(
            series,
            benchmark=benchmark,
            output=buf,
            title=title,
            download_filename=None,
        )
        raw = buf.getvalue()
    except TypeError:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tmp:
            qs.reports.html(series, benchmark=benchmark, output=tmp.name, title=title)
            tmp.flush()
            with open(tmp.name, "rb") as fh:
                raw = fh.read()
    return base64.b64encode(raw).decode("ascii")


@celery_app.task(bind=True, name="aqp.tasks.analytics_tasks.render_portfolio_tearsheet")
def render_portfolio_tearsheet(
    self,
    *,
    returns: list[float],
    index_dates: list[str] | None = None,
    benchmark_returns: list[float] | None = None,
    title: str = "AQP portfolio tearsheet",
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "rendering tearsheet", n_periods=len(returns))
    try:
        series = _build_series(returns, index_dates)
        benchmark = (
            _build_series(benchmark_returns, index_dates) if benchmark_returns else None
        )
        emit(task_id, "compute", "running quantstats", n_periods=len(returns))
        payload = _render_tearsheet_html(series, benchmark=benchmark, title=title)
        result = {
            "ok": True,
            "title": title,
            "html_base64": payload,
            "n_periods": int(len(returns)),
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("render_portfolio_tearsheet failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.analytics_tasks.compute_portfolio_metrics_async")
def compute_portfolio_metrics_async(
    self,
    *,
    returns: list[float],
    index_dates: list[str] | None = None,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, Any]:
    """Async variant of /analytics/portfolio/metrics for very long return series."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "computing portfolio metrics", n_periods=len(returns))
    try:
        import quantstats as qs

        series = _build_series(returns, index_dates)
        rfr = float(risk_free_rate)
        periods = int(periods_per_year)

        def _try(fn_name: str, *args: Any, **kwargs: Any) -> float | None:
            fn = getattr(qs.stats, fn_name, None)
            if fn is None:
                return None
            try:
                return _safe_float(fn(series, *args, **kwargs))
            except Exception:  # noqa: BLE001
                return None

        metrics = {
            "sharpe": _try("sharpe", rfr, periods),
            "sortino": _try("sortino", rfr, periods),
            "max_drawdown": _try("max_drawdown"),
            "cagr": _try("cagr"),
            "calmar": _try("calmar"),
            "tail_ratio": _try("tail_ratio"),
            "volatility": _try("volatility", periods),
        }
        result = {"ok": True, "metrics": metrics, "n_periods": len(returns)}
        emit_done(task_id, result)
        return result
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, str(exc))
        raise


__all__ = ["render_portfolio_tearsheet", "compute_portfolio_metrics_async"]
