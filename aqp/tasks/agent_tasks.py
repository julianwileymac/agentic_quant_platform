"""Celery tasks that run agentic crews.

Besides the historical behaviour (run the crew, persist an ``AgentRun``,
stream progress on ``/chat/stream/{task_id}``), the task now also updates
a lightweight :class:`CrewRun` record so the Crew Trace UI can enumerate
runs without trawling the agent_runs table.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.agent_tasks.run_research_crew")
def run_research_crew(
    self,
    prompt: str,
    session_id: str | None = None,
    config_path: str | None = None,
) -> dict[str, Any]:
    task_id = self.request.id or "local"
    emit(task_id, "start", "Starting research crew…")

    _register_crew_run(task_id, prompt, session_id=session_id)

    try:
        from aqp.agents.crew import DEFAULT_CREW_CONFIG
        from aqp.agents.crew import run_research_crew as _run
        from aqp.persistence.db import get_session
        from aqp.persistence.models import AgentRun, CrewRun

        cfg_path = Path(config_path) if config_path else DEFAULT_CREW_CONFIG

        run_id = None
        with get_session() as session:
            row = AgentRun(
                session_id=session_id,
                task_id=task_id,
                crew="research",
                status="running",
                prompt=prompt,
                started_at=datetime.utcnow(),
            )
            session.add(row)
            session.flush()
            run_id = row.id
            crew_run = session.query(CrewRun).filter(CrewRun.task_id == task_id).first()
            if crew_run is not None:
                crew_run.agent_run_id = run_id
                crew_run.status = "running"

        emit(task_id, "running", "Agents working — streaming logs…", run_id=run_id)
        result = _run(prompt, config_path=cfg_path)

        with get_session() as session:
            row = session.get(AgentRun, run_id)
            if row is not None:
                row.status = "completed"
                row.completed_at = datetime.utcnow()
                row.result = result
            crew_run = session.query(CrewRun).filter(CrewRun.task_id == task_id).first()
            if crew_run is not None:
                crew_run.status = "completed"
                crew_run.completed_at = datetime.utcnow()
                crew_run.result = result

        emit_done(task_id, result, run_id=run_id)
        return {"run_id": run_id, **result}
    except Exception as e:
        logger.exception("run_research_crew failed")
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models import CrewRun

            with get_session() as session:
                crew_run = session.query(CrewRun).filter(CrewRun.task_id == task_id).first()
                if crew_run is not None:
                    crew_run.status = "error"
                    crew_run.error = str(e)
                    crew_run.completed_at = datetime.utcnow()
        except Exception:
            logger.debug("crew_run error-stamp failed", exc_info=True)
        emit_error(task_id, str(e))
        raise


def _register_crew_run(task_id: str, prompt: str, *, session_id: str | None) -> None:
    """Insert a CrewRun row up-front so the UI can list the run immediately."""
    try:
        from aqp.persistence.db import get_session
        from aqp.persistence.models import CrewRun

        with get_session() as session:
            existing = session.query(CrewRun).filter(CrewRun.task_id == task_id).first()
            if existing is not None:
                return
            session.add(
                CrewRun(
                    task_id=task_id,
                    crew_name="research",
                    status="queued",
                    prompt=prompt,
                    session_id=session_id,
                )
            )
    except Exception:  # pragma: no cover — DB unavailable in local smoke
        logger.debug("crew_run registration skipped", exc_info=True)


@celery_app.task(name="aqp.tasks.agent_tasks.drift_check")
def drift_check() -> dict[str, Any]:
    """Scheduled: Meta-Agent reviews the ledger for anomalies."""
    try:
        from sqlalchemy import func, select

        from aqp.persistence.db import get_session
        from aqp.persistence.models import BacktestRun, LedgerEntry

        with get_session() as session:
            n_runs = session.execute(select(func.count()).select_from(BacktestRun)).scalar_one()
            n_entries = session.execute(select(func.count()).select_from(LedgerEntry)).scalar_one()
        return {"backtest_runs": n_runs, "ledger_entries": n_entries}
    except Exception as e:
        logger.exception("drift_check failed")
        return {"error": str(e)}
