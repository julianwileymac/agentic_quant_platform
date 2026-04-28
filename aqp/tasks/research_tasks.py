"""Celery tasks for research-team agents (news mining, equity, universe).

Concrete agents live under :mod:`aqp.agents.research`. Each task is a
thin wrapper that resolves the spec from the registry, builds an
:class:`AgentRuntime`, and runs it.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_spec(spec_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    from aqp.agents.registry import get_agent_spec
    from aqp.agents.runtime import AgentRuntime

    spec = get_agent_spec(spec_name)
    runtime = AgentRuntime(spec)
    return runtime.run(inputs).to_dict()


@celery_app.task(bind=True, name="aqp.tasks.research_tasks.run_news_miner")
def run_news_miner(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"news_miner inputs={list(inputs)}")
    try:
        out = _run_spec("research.news_miner", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.research_tasks.run_equity_researcher")
def run_equity_researcher(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"equity_researcher inputs={list(inputs)}")
    try:
        out = _run_spec("research.equity", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.research_tasks.run_universe_selector")
def run_universe_selector(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", f"universe_selector inputs={list(inputs)}")
    try:
        out = _run_spec("research.universe", inputs)
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise
