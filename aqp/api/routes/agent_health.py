"""``GET /agents/health`` — read-only watchdog snapshot."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from aqp.api.security import secure_router

logger = logging.getLogger(__name__)


router = secure_router(prefix="/agents", tags=["agents", "health"], default_scope="agent:view")


@router.get("/health")
def agents_health() -> dict[str, Any]:
    """Return the watchdog's running / pending / halted counts.

    Read-only: never mutates ``agent_runs_v2``. The matching mutating
    action is the Celery beat task in
    :mod:`aqp.tasks.agent_watchdog_tasks`; the topbar kill-switch can
    fan a halt out via the existing ``/agents/halt`` route.
    """
    # Inline import keeps Celery off the FastAPI route-module top
    # level (rule: no Celery imports at route module top).
    try:
        from aqp.tasks.agent_watchdog_tasks import collect_health_snapshot
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"watchdog unavailable: {exc}")
    try:
        return collect_health_snapshot()
    except Exception as exc:  # noqa: BLE001
        logger.exception("agents_health failed")
        raise HTTPException(status_code=502, detail=str(exc))


__all__ = ["router"]
