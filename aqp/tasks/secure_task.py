"""Secure Celery base task — propagates :class:`RequestContext` over headers.

Phase 3b of the AQP control-plane maturation. Closes the gap where the
HTTP layer authenticated a request, dispatched a Celery task, and the
worker had no idea who issued the work. Without this layer, broker
adapter calls / Iceberg writes / RL training runs that happen inside a
worker were untraceable to a user without bespoke per-task ``user_id``
kwargs sprinkled through the codebase.

How it works
------------

1. The HTTP route enters with a populated
   :class:`aqp.auth.context.RequestContext` bound to a contextvar via
   :func:`aqp.auth.contextvars.use_context`.
2. ``before_task_publish`` (in :mod:`aqp.tasks.celery_app`) snapshots
   the active ``RequestContext`` into a flat dict on the task message
   headers under the ``x-aqp-rctx`` key (alongside the existing
   ``x-aqp-finops`` tags).
3. The worker receives the task. Its ``__call__`` reconstructs a
   :class:`RequestContext` from the headers and binds it to the
   worker-local contextvar via :func:`use_context` so any code path
   that calls :func:`current_request_context` (the existing in-worker
   pattern across the AQP code base) sees the same identity the API
   layer authenticated.
4. The task body executes. Audit ledger writes (``LedgerWriter``,
   ``WorkloadRuntime``, ``SecurityAuditEvent``) read the
   ``RequestContext`` directly off the contextvar — no per-task kwarg
   plumbing required.

Why this is **NOT** re-authorization
------------------------------------

The API gateway already authorized the request and wrote the audit
row before dispatching. The worker DOES NOT re-validate scopes. The
``RequestContext`` it reconstructs is for **propagation** (so
downstream code that needs ``user_id`` / ``workspace_id`` /
``experiment_id`` finds them) and for **audit** (so progress frames
and ledger rows carry the same fingerprint the API layer wrote).

Reading the legacy flow
-----------------------

Pre-Phase-3b code that explicitly threaded ``user_id`` / context dicts
into task kwargs continues to work — the contextvar is a strict
addition, never a replacement. New tasks that opt into ``SecureTask``
get the contextvar populated automatically and can drop the kwargs.

Usage
-----

::

    from aqp.tasks.celery_app import celery_app
    from aqp.tasks.secure_task import SecureTask

    @celery_app.task(bind=True, base=SecureTask, queue="backtest")
    def run_backtest_task(self, config: dict) -> dict:
        ctx = self.security_ctx        # <-- always populated
        # ... dispatch through BotRuntime / RLRuntime / etc. ...
        return {"task_id": self.request.id, "user_id": ctx.user_id}
"""
from __future__ import annotations

import logging
from typing import Any

import celery

from aqp.auth.context import RequestContext, default_context
from aqp.auth.contextvars import bind_context, current_request_context

logger = logging.getLogger(__name__)


# Header key carrying the serialized RequestContext snapshot.
RCTX_HEADER_KEY = "x-aqp-rctx"


# ---------------------------------------------------------------------------
# Serialisation helpers — round-trip through JSON-serialisable dicts only
# ---------------------------------------------------------------------------


def context_to_headers(ctx: RequestContext) -> dict[str, Any]:
    """Snapshot a :class:`RequestContext` into a flat dict for task headers.

    Drops ``extras`` and ``run_id`` so the worker rebuilds the run_id
    fresh per task (each task has its own Celery task_id; the run_id
    on the worker side mirrors that). Includes both legacy and
    canonical fields so old workers reading new headers see what they
    expect.
    """
    return {
        "user_id": ctx.user_id,
        "org_id": ctx.org_id,
        "team_id": ctx.team_id,
        "workspace_id": ctx.workspace_id,
        "project_id": ctx.project_id,
        "lab_id": ctx.lab_id,
        "experiment_id": ctx.experiment_id,
        "test_id": ctx.test_id,
        "role": ctx.role,
        "live_control": bool(ctx.live_control),
    }


def headers_to_context(headers: dict[str, Any] | None) -> RequestContext:
    """Build a :class:`RequestContext` from task message headers.

    Falls back to :func:`default_context` when the headers are absent
    or malformed (older clients, externally produced messages).
    """
    if not isinstance(headers, dict) or not headers.get("user_id"):
        return default_context()
    try:
        return RequestContext(
            user_id=str(headers["user_id"]),
            org_id=_str_or_none(headers.get("org_id")),
            team_id=_str_or_none(headers.get("team_id")),
            workspace_id=_str_or_none(headers.get("workspace_id")),
            project_id=_str_or_none(headers.get("project_id")),
            lab_id=_str_or_none(headers.get("lab_id")),
            experiment_id=_str_or_none(headers.get("experiment_id")),
            test_id=_str_or_none(headers.get("test_id")),
            role=_str_or_none(headers.get("role")),
            live_control=bool(headers.get("live_control", False)),
        )
    except Exception:  # noqa: BLE001
        logger.warning("failed to rebuild RequestContext from headers; using default")
        return default_context()


def _str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


# ---------------------------------------------------------------------------
# SecureTask base class
# ---------------------------------------------------------------------------


class SecureTask(celery.Task):
    """Celery base class that binds the dispatcher's ``RequestContext``.

    Sets ``self.security_ctx`` (a :class:`RequestContext`) before the
    task body runs and binds the same context to the worker contextvar
    via :func:`bind_context` so downstream code that reads
    ``current_request_context.get()`` sees the dispatcher's identity.

    The class ALWAYS reconstructs a context (falling back to the
    local-first default). Tasks that need to enforce stricter
    behaviour can inspect ``self.security_ctx.user_id`` / ``role``
    inside the body.

    Side-effects:

    - Sets ``self.security_ctx`` on the task instance.
    - Binds the context to the worker contextvar for the duration of
      the call (released via ``finally``).
    - Logs ``celery_task_start`` / ``celery_task_success`` /
      ``celery_task_error`` records with the user_id + tenant fields
      so the audit trail correlates worker work with the originator.
    """

    abstract = True

    security_ctx: RequestContext

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        request = getattr(self, "request", None)
        raw_headers = getattr(request, "headers", None) if request else None
        rctx_headers: Any = None
        if isinstance(raw_headers, dict):
            rctx_headers = raw_headers.get(RCTX_HEADER_KEY)
        ctx = headers_to_context(rctx_headers if isinstance(rctx_headers, dict) else None)
        self.security_ctx = ctx

        task_id = getattr(request, "id", None) if request else None
        logger.info(
            "celery_task_start name=%s task_id=%s user_id=%s workspace_id=%s",
            self.name,
            task_id,
            ctx.user_id,
            ctx.workspace_id,
        )

        token = bind_context(ctx)
        try:
            result = super().__call__(*args, **kwargs)
        except Exception as exc:
            logger.error(
                "celery_task_error name=%s task_id=%s user_id=%s error=%r",
                self.name,
                task_id,
                ctx.user_id,
                str(exc),
            )
            raise
        else:
            logger.info(
                "celery_task_success name=%s task_id=%s user_id=%s",
                self.name,
                task_id,
                ctx.user_id,
            )
            return result
        finally:
            # ``bind_context`` returned the contextvar reset token;
            # restore the previous binding so other tasks on the same
            # worker don't inherit this dispatcher's identity.
            try:
                current_request_context.reset(token)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                pass


__all__ = [
    "RCTX_HEADER_KEY",
    "SecureTask",
    "context_to_headers",
    "headers_to_context",
]
