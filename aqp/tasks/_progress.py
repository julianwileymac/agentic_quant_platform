"""Shared progress-reporting helpers for Celery tasks.

Every emit includes a ``tags`` dict drawn from
:meth:`aqp.config.Settings.finops_labels` so SSE / WebSocket consumers can
filter the bus by ``cost_center`` / ``project`` / ``strategy_id`` without
re-deriving attribution. The current task's broker headers (set by the
``before_task_publish`` signal in :mod:`aqp.tasks.celery_app`) take
precedence so per-dispatch overrides flow through unchanged.
"""
from __future__ import annotations

import time
from typing import Any

from aqp.ws.broker import publish


def _current_finops_tags() -> dict[str, str]:
    """Best-effort lookup of FinOps tags for the currently executing task.

    Tries (in order):

    1. ``celery.app.current_task.request.headers["x-aqp-finops"]`` — set by
       ``before_task_publish`` for any task launched via ``.delay()``.
    2. ``aqp.config.settings.finops_labels()`` — process-wide defaults.
    3. ``{}`` if both lookups fail (silent — never crashes the bus).
    """
    try:
        from celery import current_task  # type: ignore[import-not-found]
    except Exception:  # pragma: no cover
        current_task = None  # type: ignore[assignment]
    if current_task is not None:
        request = getattr(current_task, "request", None)
        headers = getattr(request, "headers", None) or {}
        if isinstance(headers, dict):
            tags = headers.get("x-aqp-finops")
            if isinstance(tags, dict) and tags:
                return dict(tags)
        cached = getattr(current_task, "_aqp_finops", None)
        if isinstance(cached, dict) and cached:
            return dict(cached)
    try:
        from aqp.config import settings

        return settings.finops_labels()
    except Exception:  # pragma: no cover — settings might not be importable in tests
        return {}


def _context_extras(ctx: Any | None) -> dict[str, str]:
    """Project a :class:`RequestContext` into FinOps-friendly extras.

    Lazy + best-effort so this module stays importable in environments
    that haven't loaded the auth package (Celery worker boot, e.g.).
    """
    if ctx is None:
        return {}
    try:
        if hasattr(ctx, "to_finops_extras"):
            return dict(ctx.to_finops_extras())
    except Exception:  # pragma: no cover
        pass
    out: dict[str, str] = {}
    for key in ("user_id", "org_id", "team_id", "workspace_id", "project_id", "lab_id", "run_id"):
        value = getattr(ctx, key, None)
        if value:
            out[key] = str(value)
    return out


def emit(task_id: str, stage: str, message: str, *, context: Any | None = None, **extra: Any) -> None:
    payload: dict[str, Any] = {
        "task_id": task_id,
        "stage": stage,
        "message": message,
        "timestamp": time.time(),
    }
    tags = _current_finops_tags()
    if tags:
        payload["tags"] = tags
    ctx_extras = _context_extras(context)
    if ctx_extras:
        # Merge into tags so existing SSE consumers that filter by tags
        # automatically pick up workspace/project filters.
        payload.setdefault("tags", {})
        payload["tags"].update(ctx_extras)
        payload["context"] = ctx_extras
    payload.update(extra)
    publish(task_id, payload)


def emit_done(task_id: str, result: Any, *, context: Any | None = None, **extra: Any) -> None:
    emit(task_id, "done", "Task complete", context=context, result=result, **extra)


def emit_error(task_id: str, error: str, *, context: Any | None = None, **extra: Any) -> None:
    emit(task_id, "error", error, context=context, **extra)
