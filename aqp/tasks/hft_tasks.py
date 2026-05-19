"""HFT / LOB backtest Celery tasks.

Long-running tick-replay workloads. Routed to the dedicated ``hft``
Celery queue (see :mod:`aqp.tasks.celery_app`) so they don't compete
with bar-frequency backtests for the ``backtest`` queue.

Progress frame (per AGENTS rule 4)::

    {
        "task_id": "<celery-task-id>",
        "stage": "start|driving|finishing|done|error",
        "message": "<human-readable>",
        "timestamp": <unix-seconds>,
        "events_processed": <int>,
        "equity": <float>,
        "position": <float>,
    }
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aqp.core.registry import resolve
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app
from aqp.tasks.secure_task import SecureTask

logger = logging.getLogger(__name__)


_PROGRESS_INTERVAL_SEC = 2.0


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.hft_tasks.run_lob_backtest")
def run_lob_backtest(
    self,
    *,
    strategy_alias: str = "AvellanedaStoikovMM",
    strategy_kwargs: dict[str, Any] | None = None,
    dataset_preset: str | None = None,
    feeds: list[str] | None = None,
    latency_profile: str = "intp_order_latency",
    queue_model: str = "probabilistic",
    tick_size: float = 0.01,
    lot_size: float = 0.001,
    max_events: int = 1_000_000,
    snapshot_every: int = 5_000,
) -> dict[str, Any]:
    """Run a LOB backtest on the ``hft`` queue.

    Resolves a strategy by registry alias, instantiates it with the
    supplied kwargs, and feeds it through
    :class:`aqp.backtest.hft.LobBacktestEngine`. Streams progress every
    ~2 s so a UI consumer can watch a long replay.

    Returns a dict containing ``summary`` (the merged HFT summary +
    metric tiles) plus run metadata. The full equity curve is *not*
    serialised back through Celery — clients pull it from the trade /
    order DataFrames via a follow-up read of the task result.
    """
    task_id = self.request.id or "local"
    emit(
        task_id,
        "start",
        f"loading strategy={strategy_alias} preset={dataset_preset}",
        events_processed=0,
    )

    try:
        cls = resolve(strategy_alias)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"unknown strategy {strategy_alias!r}: {exc}")
        raise

    try:
        strategy = cls(**(strategy_kwargs or {}))
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"strategy {strategy_alias} __init__ failed: {exc}")
        raise

    last_emit = time.time()

    def progress_callback(
        *, events_processed: int, equity: float, position: float
    ) -> None:
        nonlocal last_emit
        now = time.time()
        if now - last_emit < _PROGRESS_INTERVAL_SEC:
            return
        last_emit = now
        emit(
            task_id,
            "driving",
            f"events={events_processed} equity={equity:.2f} position={position:.4f}",
            events_processed=int(events_processed),
            equity=float(equity),
            position=float(position),
        )

    try:
        from aqp.backtest.hft import LobBacktestEngine

        engine = LobBacktestEngine(
            latency_profile=latency_profile,
            queue_model=queue_model,
            tick_size=float(tick_size),
            lot_size=float(lot_size),
            progress_callback=progress_callback,
        )
        result = engine.run(
            strategy,
            feeds=feeds,
            dataset_preset=dataset_preset,
            max_events=int(max_events),
            snapshot_every=int(snapshot_every),
        )
    except ImportError as exc:
        emit_error(task_id, f"hft extras missing: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"backtest failed: {exc}")
        logger.exception("LOB backtest failed")
        raise

    emit(
        task_id,
        "finishing",
        f"computed metrics — final equity={result.final_equity:.2f}",
        events_processed=int(result.summary.get("events_processed", 0)),
        equity=float(result.final_equity),
    )

    payload: dict[str, Any] = {
        "strategy": strategy_alias,
        "dataset_preset": dataset_preset,
        "feeds": feeds,
        "summary": dict(result.summary),
        "n_trades": int(len(result.trades)),
        "n_orders": int(len(result.orders)),
        "initial_cash": float(result.initial_cash),
        "final_equity": float(result.final_equity),
        "start": result.start.isoformat() if result.start else None,
        "end": result.end.isoformat() if result.end else None,
    }
    emit_done(task_id, payload)
    return payload


__all__ = ["run_lob_backtest"]
