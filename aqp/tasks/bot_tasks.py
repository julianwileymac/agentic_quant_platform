"""Celery tasks for the Bot entity (backtest / paper / chat / deploy).

All tasks share the same lifecycle:

1. Resolve the bot by ``bot_id`` (Postgres) **or** ``slug`` (registry).
2. Build the right :class:`BaseBot` subclass via :func:`build_bot`.
3. Drive execution through :class:`BotRuntime`, which:

   - Snapshots the spec into ``bot_versions`` (hash-locked).
   - Opens a ``bot_deployments`` row for telemetry.
   - Emits progress through :mod:`aqp.tasks._progress` so the existing
     ``/chat/stream/<task_id>`` WebSocket consumers light up unchanged.

Hard-rule reminder: agent / chat tasks invoke
:class:`aqp.agents.runtime.AgentRuntime`; they never call
``router_complete`` directly.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_bot(bot_ref: str) -> Any:
    """Resolve ``bot_ref`` to a :class:`BaseBot` instance.

    Lookup order:

    1. Postgres ``bots`` row by id (UUID-shaped string).
    2. Postgres ``bots`` row by slug.
    3. In-memory :func:`get_bot_spec` registry by name (YAML / decorator).
    """
    from aqp.bots.base import build_bot
    from aqp.bots.registry import get_bot_spec
    from aqp.bots.spec import BotSpec
    from aqp.persistence.db import SessionLocal
    from aqp.persistence.models_bots import Bot as BotRow

    project_id: str | None = None
    spec: BotSpec | None = None
    bot_id: str | None = None
    try:
        with SessionLocal() as session:
            row = session.get(BotRow, bot_ref) if _looks_like_uuid(bot_ref) else None
            if row is None:
                row = session.query(BotRow).filter(BotRow.slug == bot_ref).one_or_none()
            if row is not None:
                if row.spec_yaml:
                    spec = BotSpec.from_yaml_str(row.spec_yaml)
                bot_id = row.id
                project_id = row.project_id
    except Exception:  # noqa: BLE001
        logger.debug("DB lookup for bot %s failed; falling back to registry", bot_ref, exc_info=True)
    if spec is None:
        spec = get_bot_spec(bot_ref)
    return build_bot(spec, bot_id=bot_id, project_id=project_id)


def _looks_like_uuid(value: str) -> bool:
    return isinstance(value, str) and len(value) == 36 and value.count("-") == 4


@celery_app.task(bind=True, name="aqp.tasks.bot_tasks.run_bot_backtest")
def run_bot_backtest(
    self,
    bot_ref: str,
    *,
    run_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an offline backtest for the bot identified by id / slug / name."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Loading bot {bot_ref!r}…")
    try:
        from aqp.bots.runtime import BotRuntime

        bot = _load_bot(bot_ref)
        runtime = BotRuntime(bot, task_id=task_id)
        result = runtime.backtest(run_name=run_name, overrides=overrides or {})
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_bot_backtest failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.bot_tasks.run_bot_paper")
def run_bot_paper(
    self,
    bot_ref: str,
    *,
    run_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Launch the bot's paper-trading session inside the Celery worker."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Starting paper session for bot {bot_ref!r}…")
    try:
        from aqp.bots.runtime import BotRuntime

        bot = _load_bot(bot_ref)
        runtime = BotRuntime(bot, task_id=task_id)
        result = runtime.paper(run_name=run_name, overrides=overrides or {})
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("run_bot_paper failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.bot_tasks.chat_research_bot")
def chat_research_bot(
    self,
    bot_ref: str,
    prompt: str,
    *,
    session_id: str | None = None,
    agent_role: str | None = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Drive a single chat turn for a :class:`ResearchBot` via :class:`AgentRuntime`."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Chatting with bot {bot_ref!r}…")
    try:
        from aqp.bots.research_bot import ResearchBot
        from aqp.bots.runtime import BotRuntime

        bot = _load_bot(bot_ref)
        if not isinstance(bot, ResearchBot):
            raise TypeError(
                f"Bot {bot_ref!r} is kind={bot.spec.kind!r}; chat is ResearchBot-only"
            )
        runtime = BotRuntime(bot, task_id=task_id, session_id=session_id)
        result = runtime.chat(prompt, session_id=session_id, agent_role=agent_role)
        payload = result.to_dict()
        if inputs:
            payload.setdefault("inputs", inputs)
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("chat_research_bot failed")
        emit_error(task_id, str(exc))
        raise


@celery_app.task(bind=True, name="aqp.tasks.bot_tasks.deploy_bot")
def deploy_bot(
    self,
    bot_ref: str,
    *,
    target: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deploy the bot via the configured target (``paper_session`` or ``kubernetes``)."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Deploying bot {bot_ref!r} (target={target or 'spec-default'})…")
    try:
        from aqp.bots.runtime import BotRuntime

        bot = _load_bot(bot_ref)
        runtime = BotRuntime(bot, task_id=task_id)
        result = runtime.deploy(target=target, overrides=overrides or {})
        payload = result.to_dict()
        emit_done(task_id, payload)
        return payload
    except Exception as exc:  # pragma: no cover
        logger.exception("deploy_bot failed")
        emit_error(task_id, str(exc))
        raise


__all__ = [
    "chat_research_bot",
    "deploy_bot",
    "run_bot_backtest",
    "run_bot_paper",
]
