"""Helper that persists Selection-agent annotations into agent_annotations.

The :class:`AnnotationTool` covers the agent-tool path; this helper is
for callers that want to write annotations from Python (e.g. backtest
runners) without going through CrewAI.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def write_selection_annotation(
    *,
    spec_name: str = "selection.stock_selector",
    run_id: str | None = None,
    vt_symbol: str | None = None,
    label: str = "pick",
    notes: str = "",
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Persist one annotation row, returning its id."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_agents import AgentAnnotation

        with SessionLocal() as session:
            row = AgentAnnotation(
                spec_name=spec_name,
                run_id=run_id,
                vt_symbol=vt_symbol,
                label=label,
                notes=notes,
                payload=payload or {},
            )
            session.add(row)
            session.commit()
            return row.id
    except Exception:  # noqa: BLE001
        logger.debug("Could not write selection annotation", exc_info=True)
        return None


__all__ = ["write_selection_annotation"]
