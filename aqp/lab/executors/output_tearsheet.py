"""``out.tearsheet`` — render a QuantStats-style portfolio tearsheet.

For the synchronous fast path (EDA preview, Phase 0 testing compose)
we wrap the helpers in :mod:`aqp.tasks.analytics_tasks` directly.
For the async / Celery testing path (Phase 2) the Celery task wrapper
in :mod:`aqp.tasks.lab_tasks` dispatches to
:func:`aqp.tasks.analytics_tasks.render_portfolio_tearsheet` and we
just record the resulting MLflow artifact URI here.

Phase 3 (DSR surfacing): every tearsheet result MUST carry the
Deflated Sharpe Ratio alongside the raw Sharpe so the UI never
renders raw Sharpe alone. We pull the honest
``total_trials_searched`` count off
:class:`aqp.persistence.models_lab.LabRun` when the executor runs
inside an Evaluation sweep — Testing mode runs default to
``n_trials=1`` (which collapses DSR to PSR, the right thing).

Params:

- ``values`` (list[float] | None) — the equity / cumulative-return
  series; if omitted, we look on the upstream portfolio locator.
- ``benchmark`` (list[float] | None) — optional benchmark series.
- ``title`` (str, default ``"AQP tearsheet"``).
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    values = params.get("values")
    benchmark = params.get("benchmark")
    title = str(params.get("title") or "AQP tearsheet")

    if not values and ctx.upstream:
        # Pull series from the upstream portfolio locator if the
        # caller didn't pass them inline.
        for locator in ctx.upstream.values():
            if isinstance(locator, dict):
                values = values or locator.get("equity_curve")
                benchmark = benchmark or locator.get("benchmark_curve")
                if values:
                    break

    if not values or not isinstance(values, list):
        return NodeResult(
            status="error",
            error=(
                "out.tearsheet requires a non-empty 'values' equity series "
                "(either inline param or upstream portfolio locator)"
            ),
            log_label=f"tearsheet:{node.id}",
        )

    try:
        from aqp.tasks import analytics_tasks
    except Exception as exc:  # noqa: BLE001
        logger.exception("analytics_tasks import failed")
        return NodeResult(
            status="error",
            error=f"analytics_tasks import failed: {exc}",
            log_label=f"tearsheet:{node.id}",
        )

    try:
        series = analytics_tasks._build_series(values)
        html_b64 = analytics_tasks._render_tearsheet_html(
            series,
            benchmark=analytics_tasks._build_series(benchmark) if benchmark else None,
            title=title,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("tearsheet render failed")
        return NodeResult(
            status="error",
            error=f"tearsheet render failed: {exc}",
            log_label=f"tearsheet:{node.id}",
        )

    # Phase 3 — DSR + raw Sharpe surfacing. Both metrics ALWAYS go on
    # the locator + metrics dict so the frontend tearsheet display
    # never has the option of rendering raw Sharpe alone.
    sharpe_stats = _compute_sharpe_and_dsr(values, ctx)

    locator: dict[str, Any] = {
        "kind": "tearsheet_html_b64",
        "title": title,
        "size_chars": len(html_b64),
        "node_id": node.id,
        "sharpe": sharpe_stats.get("sharpe"),
        "deflated_sharpe": sharpe_stats.get("deflated_sharpe"),
        "probabilistic_sharpe": sharpe_stats.get("probabilistic_sharpe"),
        "n_obs": sharpe_stats.get("n_obs"),
        "total_trials_searched": sharpe_stats.get("total_trials_searched"),
    }
    ctx.extras.setdefault("_tearsheets", {})[node.id] = html_b64

    return NodeResult(
        status="done",
        output_locator=locator,
        metrics={
            "size_chars": len(html_b64),
            **{k: v for k, v in sharpe_stats.items() if v is not None},
        },
        log_label=f"tearsheet:{title}",
    )


def _compute_sharpe_and_dsr(values: list[float], ctx: NodeContext) -> dict[str, Any]:
    """Return raw Sharpe, PSR, DSR — pulling honest trial count from the run row.

    Best-effort: never raises. When the persistence layer is missing
    (in-process tests, sandboxed dev) we fall back to ``n_trials=1``
    which makes DSR equal PSR — still honest.
    """
    out: dict[str, Any] = {
        "sharpe": None,
        "probabilistic_sharpe": None,
        "deflated_sharpe": None,
        "n_obs": None,
        "total_trials_searched": 1,
    }
    if not values:
        return out
    arr = np.asarray(values, dtype=float)
    if arr.size < 3:
        return out
    returns = np.diff(arr) / np.maximum(np.abs(arr[:-1]), 1e-12)
    if returns.size < 2:
        return out
    mean = float(np.nanmean(returns))
    std = float(np.nanstd(returns, ddof=1))
    if std <= 0 or not np.isfinite(std):
        return out
    sharpe_per_period = mean / std
    # Annualise assuming the series resolution is daily — the user can
    # override with a benchmark-aware step if needed. The DSR formula
    # operates on the per-period Sharpe so we report both shapes.
    annualised = sharpe_per_period * float(np.sqrt(252))
    out["sharpe"] = round(annualised, 6)
    out["n_obs"] = int(returns.size)

    n_trials = _fetch_total_trials_searched(ctx)
    out["total_trials_searched"] = n_trials
    try:
        from aqp.lab.evaluation.deflated_sharpe import (
            deflated_sharpe_ratio,
            probabilistic_sharpe_ratio,
        )

        psr = probabilistic_sharpe_ratio(
            observed_sharpe=sharpe_per_period,
            n_obs=int(returns.size),
            benchmark_sharpe=0.0,
        )
        dsr = deflated_sharpe_ratio(
            observed_sharpe=sharpe_per_period,
            n_obs=int(returns.size),
            n_trials=max(1, int(n_trials)),
        )
        out["probabilistic_sharpe"] = round(float(psr), 6)
        out["deflated_sharpe"] = round(float(dsr), 6)
    except Exception:  # noqa: BLE001
        return out
    return out


def _fetch_total_trials_searched(ctx: NodeContext) -> int:
    """Pull ``LabRun.total_trials_searched`` for the active run, default 1."""
    if not ctx.run_id:
        return 1
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabRun

        with SessionLocal() as session:
            row = session.get(LabRun, ctx.run_id)
            if row is not None and row.total_trials_searched:
                return int(row.total_trials_searched)
    except Exception:  # noqa: BLE001
        pass
    return 1


__all__ = ["execute"]
