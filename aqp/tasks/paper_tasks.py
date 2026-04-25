"""Celery tasks for paper / live trading sessions.

Stop signalling is relayed through Redis on the key
``aqp:paper:<task_id>:stop``; the in-process session subscribes via
:func:`subscribe_stop_signal` and drains gracefully on first message.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from dataclasses import asdict
from typing import Any

from aqp.config import settings
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _stop_key(task_id: str) -> str:
    return f"aqp:paper:{task_id}:stop"


def publish_stop_signal(task_id: str, reason: str = "manual") -> None:
    """Publish a Redis message telling an in-flight paper task to shut down."""
    import redis

    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    client.set(_stop_key(task_id), reason, ex=60)
    client.publish(_stop_key(task_id), reason)


async def _watch_stop_signal(task_id: str, session: Any) -> None:
    """Background task listening for the stop signal and calling ``request_shutdown``."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        # Prime: check the key in case the signal fires before subscribe.
        existing = await client.get(_stop_key(task_id))
        if existing:
            session.request_shutdown(str(existing))
            return
        pubsub = client.pubsub()
        await pubsub.subscribe(_stop_key(task_id))
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            session.request_shutdown(str(message.get("data") or "remote"))
            break
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("stop-signal watcher error for %s", task_id)
    finally:
        await client.close()


@celery_app.task(bind=True, name="aqp.tasks.paper_tasks.run_paper")
def run_paper(
    self,
    cfg: dict[str, Any],
    run_name: str = "paper-adhoc",
) -> dict[str, Any]:
    """Launch an async paper trading session and await completion."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Starting paper session: {run_name}")
    try:
        from aqp.trading.runner import run_paper_session_from_config_async
        from aqp.trading.session import PaperTradingSession

        async def _run() -> dict[str, Any]:
            # Build-then-run so we can attach the stop-signal watcher.
            from aqp.trading.runner import build_session_from_config

            session: PaperTradingSession = build_session_from_config(cfg, task_id=task_id)
            if run_name:
                session.config.run_name = run_name
            watcher = asyncio.create_task(_watch_stop_signal(task_id, session))
            try:
                result = await session.run()
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await watcher
            return asdict(result)

        # Reuse the async helper if the caller didn't need stop-signals.
        if cfg.get("_use_async_helper"):
            result = asyncio.run(run_paper_session_from_config_async(cfg, run_name=run_name, task_id=task_id))
            result_dict = asdict(result)
        else:
            result_dict = asyncio.run(_run())

        emit_done(task_id, result_dict)
        return result_dict
    except Exception as exc:  # pragma: no cover
        logger.exception("paper task failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(name="aqp.tasks.paper_tasks.stop_paper")
def stop_paper(task_id: str, reason: str = "manual") -> dict[str, Any]:
    """Send the stop signal to an in-flight paper session."""
    publish_stop_signal(task_id, reason)
    return {"task_id": task_id, "reason": reason, "ok": True}


# Convenience sync runner useful from the ``aqp paper run`` CLI (no Celery).
def run_paper_blocking(cfg: dict[str, Any], run_name: str = "paper-adhoc") -> dict[str, Any]:
    """Run a paper session synchronously (no task_id, no Celery, no stop-signal)."""
    from aqp.trading.runner import run_paper_session_from_config

    return run_paper_session_from_config(cfg, run_name=run_name)


__all__ = ["publish_stop_signal", "run_paper", "run_paper_blocking", "stop_paper"]


# Thread-local buffer so unit tests can call stop_paper without a live Redis.
_local = threading.local()