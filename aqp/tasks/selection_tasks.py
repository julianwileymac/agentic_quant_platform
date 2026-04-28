"""Celery tasks for the selection-agent team."""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.selection_tasks.run_stock_selector")
def run_stock_selector(self, **inputs: Any) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "stock_selector")
    try:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        spec = get_agent_spec("selection.stock_selector")
        out = AgentRuntime(spec).run(inputs).to_dict()
        emit_done(task_id, out)
        return out
    except Exception as exc:  # pragma: no cover
        emit_error(task_id, str(exc))
        raise
