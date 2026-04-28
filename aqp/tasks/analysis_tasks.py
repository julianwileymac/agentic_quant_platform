"""Celery tasks for the analysis-agent team (step / run / portfolio interpreters)."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run(spec: str, inputs: dict[str, Any]) -> dict[str, Any]:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    return AgentRuntime(get_agent_spec(spec)).run(inputs).to_dict()


@celery_app.task(bind=True, name="aqp.tasks.analysis_tasks.analyze_step")
def analyze_step(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "analysis.step")
    try:
        out = _run("analysis.step", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.analysis_tasks.analyze_run")
def analyze_run(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "analysis.run")
    try:
        out = _run("analysis.run", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.analysis_tasks.analyze_portfolio")
def analyze_portfolio(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "analysis.portfolio")
    try:
        out = _run("analysis.portfolio", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.analysis_tasks.reflect")
def reflect(self, **inputs: Any) -> dict[str, Any]:
    """Trigger TradingAgents-style deferred outcome reflection."""
    task_id = self.request.id or "local"
    emit(task_id, "start", "analysis.reflector")
    try:
        from aqp.agents.analysis.reflector import run_reflection_pass

        out = run_reflection_pass(**inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise
