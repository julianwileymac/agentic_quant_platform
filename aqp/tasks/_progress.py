"""Shared progress-reporting helpers for Celery tasks."""
from __future__ import annotations

import time
from typing import Any

from aqp.ws.broker import publish


def emit(task_id: str, stage: str, message: str, **extra: Any) -> None:
    publish(
        task_id,
        {
            "task_id": task_id,
            "stage": stage,
            "message": message,
            "timestamp": time.time(),
            **extra,
        },
    )


def emit_done(task_id: str, result: Any, **extra: Any) -> None:
    emit(task_id, "done", "Task complete", result=result, **extra)


def emit_error(task_id: str, error: str, **extra: Any) -> None:
    emit(task_id, "error", error, **extra)
