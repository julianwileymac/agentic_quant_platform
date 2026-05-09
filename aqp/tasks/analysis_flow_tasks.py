"""Celery tasks for the analysis-FLOW umbrella.

NB: this module is intentionally distinct from
:mod:`aqp.tasks.analysis_tasks` (which hosts the analysis-AGENTS
interpretation tasks). Both share the ``agents`` queue but they are
separate code paths — see [docs/analysis-framework.md] vs
[docs/analysis-agents.md].

Two tasks:

- :func:`preview_analysis_flow` — sync-shaped Celery wrapper around
  :meth:`AnalysisRuntime.preview` for one-shot fan-out. The same
  endpoint (``POST /analysis/flows/{flow}/preview``) calls the
  underlying runtime directly when sync execution is fine.
- :func:`run_analysis_spec` — full :meth:`AnalysisRuntime.run` driver.
  Looks up the spec by slug, invokes the runtime, and emits progress
  through :mod:`aqp.tasks._progress` (rule #4).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.analysis_flow_tasks.preview_analysis_flow")
def preview_analysis_flow(
    self,
    flow: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Synchronous preview wrapper.

    ``payload`` shape: ``{"params": {...}, "dataset_cfg": {...}}``.
    The runtime is constructed in preview mode (``spec=None``).
    """
    from aqp.analysis.runtime import AnalysisRuntime
    from aqp.core.registry import build_from_config

    payload = payload or {}
    params = payload.get("params") or {}
    dataset_cfg = payload.get("dataset_cfg") or {}
    df: Any = None
    try:
        if dataset_cfg:
            handler = build_from_config(dataset_cfg)
            df = handler.fetch() if hasattr(handler, "fetch") else handler
    except Exception as exc:  # noqa: BLE001
        emit_error(self.request.id, f"dataset build failed: {exc}")
        raise
    emit(self.request.id, "running", f"preview {flow}")
    try:
        runtime = AnalysisRuntime(task_id=self.request.id)
        result = runtime.preview(flow, df, params)
        out = result.to_dict()
        emit_done(self.request.id, out)
        return out
    except Exception as exc:
        emit_error(self.request.id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.analysis_flow_tasks.run_analysis_spec")
def run_analysis_spec(
    self,
    spec_slug: str | None = None,
    spec_payload: dict[str, Any] | None = None,
    *,
    target: str = "run",
) -> dict[str, Any]:
    """Drive :meth:`AnalysisRuntime.run` via Celery.

    ``spec_slug`` resolves a registered spec; ``spec_payload`` is an
    inline JSON payload that becomes a fresh :class:`AnalysisSpec`.
    Exactly one of the two MUST be provided.
    """
    from aqp.analysis.runtime import AnalysisRuntime
    from aqp.analysis.spec import AnalysisSpec
    from aqp.analysis.registry import get_analysis_spec

    if spec_payload:
        spec = AnalysisSpec.model_validate(spec_payload)
    elif spec_slug:
        spec = get_analysis_spec(spec_slug)
    else:
        raise ValueError("either spec_slug or spec_payload is required")

    runtime = AnalysisRuntime(spec, task_id=self.request.id)
    try:
        result = runtime.run() if target == "run" else runtime.run()
        out = result.to_dict()
        if result.status == "completed":
            emit_done(self.request.id, out)
        else:
            emit_error(self.request.id, result.error or "analysis failed")
        return out
    except Exception as exc:
        emit_error(self.request.id, str(exc))
        raise
