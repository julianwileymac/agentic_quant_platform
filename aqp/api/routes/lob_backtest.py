"""``/backtest/lob`` — HFT / LOB backtest REST surface.

Wraps :func:`aqp.tasks.hft_tasks.run_lob_backtest` so the webui can
launch + monitor a tick-replay backtest. Long-running; returns a
:class:`aqp.api.schemas.TaskAccepted` and the caller subscribes to the
existing progress WebSocket at ``/chat/stream/{task_id}``.

Endpoints
=========

- ``POST /backtest/lob`` — enqueue a backtest job. Body picks the
  strategy alias (registered in :class:`aqp.core.registry`), the gz
  feed paths or dataset preset, and the latency / queue model.
- ``GET /backtest/lob/{task_id}`` — return the Celery result + status.

Per AGENTS rule "Don't put Celery imports at FastAPI route module
top level": every Celery import is inlined inside the route handler.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.schemas import TaskAccepted

logger = logging.getLogger(__name__)

router = secure_router(prefix="/backtest/lob", tags=["backtest"], default_scope="trade:read")


class LobBacktestRequest(BaseModel):
    strategy: str = Field(
        ...,
        description=(
            "Registered strategy alias under aqp.strategies.hft "
            "(e.g. AvellanedaStoikovMM, GLFTMM, GridMM, ImbalanceAlphaMM, "
            "BasisAlphaMM, QueueAwareMM)."
        ),
    )
    strategy_kwargs: dict[str, Any] | None = Field(
        default=None, description="Per-strategy __init__ kwargs override."
    )
    dataset_preset: str | None = Field(
        default=None,
        description=(
            "Bundled preset name (e.g. 'lob_btcusdt_sample') resolved "
            "via aqp.data.dataset_presets."
        ),
    )
    feeds: list[str] | None = Field(
        default=None,
        description=(
            "Explicit gz feed paths. Mutually exclusive with dataset_preset; "
            "exactly one must be set."
        ),
    )
    latency_profile: str = "intp_order_latency"
    queue_model: str = "probabilistic"
    tick_size: float = 0.01
    lot_size: float = 0.001
    max_events: int = Field(default=1_000_000, ge=10_000, le=100_000_000)
    snapshot_every: int = Field(default=5_000, ge=100, le=1_000_000)


class LobBacktestStatus(BaseModel):
    task_id: str
    status: str
    summary: dict[str, Any] | None = None
    error: str | None = None


@router.post("", response_model=TaskAccepted, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_lob_backtest(request: LobBacktestRequest) -> TaskAccepted:
    """Enqueue an HFT LOB backtest. Returns the Celery task id + stream URL."""
    if not request.dataset_preset and not request.feeds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must supply either 'dataset_preset' or 'feeds'.",
        )
    if request.dataset_preset and request.feeds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pass exactly one of 'dataset_preset' or 'feeds', not both.",
        )

    # Inline import (AGENTS rule: no Celery imports at route module top level).
    from aqp.tasks.hft_tasks import run_lob_backtest

    async_result = run_lob_backtest.delay(
        strategy_alias=request.strategy,
        strategy_kwargs=request.strategy_kwargs,
        dataset_preset=request.dataset_preset,
        feeds=request.feeds,
        latency_profile=request.latency_profile,
        queue_model=request.queue_model,
        tick_size=request.tick_size,
        lot_size=request.lot_size,
        max_events=request.max_events,
        snapshot_every=request.snapshot_every,
    )
    task_id = async_result.id or "local"
    return TaskAccepted(
        task_id=task_id,
        status="queued",
        stream_url=f"/chat/stream/{task_id}",
    )


@router.get("/{task_id}", response_model=LobBacktestStatus)
async def get_lob_backtest_status(task_id: str) -> LobBacktestStatus:
    """Retrieve the Celery state + result for a LOB backtest."""
    from aqp.tasks.celery_app import celery_app

    async_result = celery_app.AsyncResult(task_id)
    state = async_result.state or "PENDING"

    summary: dict[str, Any] | None = None
    error: str | None = None
    if state == "SUCCESS":
        try:
            result = async_result.result
            if isinstance(result, dict):
                summary = result
        except Exception as exc:  # noqa: BLE001
            error = f"failed to fetch result: {exc}"
    elif state == "FAILURE":
        try:
            error = str(async_result.result)
        except Exception:  # noqa: BLE001
            error = "task failed"

    return LobBacktestStatus(
        task_id=task_id,
        status=state.lower(),
        summary=summary,
        error=error,
    )


__all__ = ["router"]
