"""``BotRuntime`` — execute a :class:`BotSpec` end-to-end with telemetry.

The runtime is the single sanctioned execution entry for any bot:

1. Snapshot + persist the spec version (hash-locked → ``bot_versions``).
2. Open a :class:`BotDeployment` row so the UI can correlate progress
   updates back to a durable record.
3. Drive the underlying execution (backtest, paper session, chat,
   deploy) by reusing the existing primitives — the runtime never
   re-implements them.
4. Emit progress through :mod:`aqp.tasks._progress` so the existing
   ``/chat/stream/<task_id>`` WebSocket consumers light up unchanged.
5. Finalise the deployment row with status + ``result_summary``.

Hard rule: agent invocations go through :class:`AgentRuntime`. The bot
runtime never calls ``router_complete`` directly.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from aqp.bots.spec import BotSpec
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


@dataclass
class BotRunResult:
    """Outcome of any :class:`BotRuntime` action.

    The ``status`` follows the Celery convention used elsewhere
    (``running`` → ``completed`` / ``error`` / ``cancelled``); the
    ``result`` payload mirrors the underlying primitive (backtest dict,
    paper session asdict, agent run dict, k8s manifest dict).
    """

    deployment_id: str | None
    bot_id: str | None
    target: str
    status: str
    started_at: float
    duration_ms: float = 0.0
    task_id: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BotRuntime:
    """Executor for a single :class:`BaseBot`."""

    def __init__(
        self,
        bot: Any,  # aqp.bots.base.BaseBot, but typed loose to avoid cycles
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        context: Any | None = None,
    ) -> None:
        self.bot = bot
        self.spec: BotSpec = bot.spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        self.session_id = session_id
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:
                context = None
        self.context = context

    # ----------------------------------------------------------- public API

    def backtest(
        self,
        *,
        run_name: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> BotRunResult:
        """Run an offline backtest and persist a deployment row."""
        return self._with_deployment(
            target="backtest",
            stage_message=f"Backtesting bot {self.spec.name!r}",
            action=lambda: self.bot.backtest(run_name=run_name, **(overrides or {})),
        )

    def paper(
        self,
        *,
        run_name: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> BotRunResult:
        """Build + run a paper session synchronously (Celery-friendly)."""
        run_kwargs = overrides or {}

        def _action() -> dict[str, Any]:
            session = self.bot.paper(run_name=run_name, **run_kwargs)
            session.task_id = self.task_id
            result = asyncio.run(session.run())
            return asdict(result)

        return self._with_deployment(
            target="paper_session",
            stage_message=f"Paper-trading bot {self.spec.name!r}",
            action=_action,
        )

    def chat(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        agent_role: str | None = None,
    ) -> BotRunResult:
        """Conversational entry. Routes through :class:`AgentRuntime`.

        :class:`TradingBot` raises ``BotMethodNotSupported``; only
        :class:`ResearchBot` exposes a meaningful chat surface.
        """
        return self._with_deployment(
            target="chat",
            stage_message=f"Chatting with bot {self.spec.name!r}",
            action=lambda: self.bot.chat(prompt, session_id=session_id, agent_role=agent_role),
        )

    def deploy(
        self,
        *,
        target: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> BotRunResult:
        """Dispatch to the configured deployment target.

        Phase 1 supports ``paper_session`` and ``backtest_only``; Phase 5
        will add ``kubernetes``. The dispatcher writes its own
        :class:`BotDeployment` row so this wrapper just streams progress.
        """
        return self._with_deployment(
            target=target or self.spec.deployment.target,
            stage_message=f"Deploying bot {self.spec.name!r}",
            action=lambda: self.bot.deploy(target=target, **(overrides or {})),
        )

    # ----------------------------------------------------------- DB plumbing

    def _snapshot_spec(self) -> str | None:
        from aqp.bots.registry import persist_spec

        return persist_spec(self.spec, project_id=getattr(self.bot, "project_id", None))

    def _open_deployment(
        self,
        *,
        target: str,
        version_id: str | None,
    ) -> str | None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_bots import Bot as BotRow
            from aqp.persistence.models_bots import BotDeployment

            with SessionLocal() as session:
                bot_row = (
                    session.query(BotRow)
                    .filter(BotRow.slug == self.spec.slug)
                    .one_or_none()
                )
                row = BotDeployment(
                    id=str(uuid.uuid4()),
                    bot_id=bot_row.id if bot_row is not None else None,
                    version_id=version_id,
                    target=target,
                    task_id=self.task_id,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.flush()
                return row.id
        except Exception:  # noqa: BLE001
            logger.debug("Could not open bot_deployment row", exc_info=True)
            return None

    def _finalise_deployment(
        self,
        deployment_id: str | None,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: str | None,
        manifest_yaml: str | None = None,
    ) -> None:
        if deployment_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_bots import BotDeployment

            with SessionLocal() as session:
                row = session.get(BotDeployment, deployment_id)
                if row is None:
                    return
                row.status = status
                row.result_summary = _safe_json(result) or {}
                row.error = error
                row.ended_at = datetime.utcnow()
                if manifest_yaml is not None:
                    row.manifest_yaml = manifest_yaml
        except Exception:  # noqa: BLE001
            logger.debug("Could not finalise bot_deployment row", exc_info=True)

    def _stamp_tenancy(self, row: Any) -> None:
        ctx = self.context
        if ctx is None:
            return
        for attr_ctx, attr_row in (
            ("user_id", "owner_user_id"),
            ("workspace_id", "workspace_id"),
            ("project_id", "project_id"),
        ):
            value = getattr(ctx, attr_ctx, None)
            if value and hasattr(row, attr_row) and getattr(row, attr_row, None) in (None, ""):
                setattr(row, attr_row, value)

    # ----------------------------------------------------------- core driver

    def _with_deployment(
        self,
        *,
        target: str,
        stage_message: str,
        action,
    ) -> BotRunResult:
        started = time.time()
        version_id = self._snapshot_spec()
        deployment_id = self._open_deployment(target=target, version_id=version_id)
        self._emit_progress("start", stage_message, deployment_id=deployment_id, target=target)
        status = "running"
        error: str | None = None
        result: dict[str, Any] = {}
        try:
            self._emit_progress("running", f"{stage_message} …", deployment_id=deployment_id)
            raw = action()
            if isinstance(raw, dict):
                result = raw
            elif raw is None:
                result = {}
            elif hasattr(raw, "to_dict"):
                result = raw.to_dict()
            elif hasattr(raw, "__dict__"):
                result = dict(vars(raw))
            else:
                result = {"value": str(raw)}
            status = result.get("status", "completed") if isinstance(result, dict) else "completed"
        except Exception as exc:  # noqa: BLE001
            logger.exception("BotRuntime action failed for %s", self.spec.name)
            status = "error"
            error = str(exc)
            if self.task_id:
                emit_error(self.task_id, error, context=self.context)
        finally:
            self._finalise_deployment(
                deployment_id,
                status=status,
                result=result,
                error=error,
                manifest_yaml=result.get("manifest_yaml") if isinstance(result, dict) else None,
            )
        if status == "completed" and self.task_id:
            emit_done(self.task_id, result, context=self.context)
        return BotRunResult(
            deployment_id=deployment_id,
            bot_id=getattr(self.bot, "bot_id", None),
            target=target,
            status=status,
            started_at=started,
            duration_ms=(time.time() - started) * 1000.0,
            task_id=self.task_id,
            result=result if isinstance(result, dict) else {"value": str(result)},
            error=error,
        )

    # ----------------------------------------------------------- progress

    def _emit_progress(self, stage: str, message: str, **extra: Any) -> None:
        logger.info("[bot:%s] %s: %s", self.spec.slug, stage, message)
        if not self.task_id:
            return
        emit(
            self.task_id,
            stage,
            message,
            context=self.context,
            run_id=self.run_id,
            bot_slug=self.spec.slug,
            **extra,
        )


def _safe_json(value: Any) -> Any:
    import json

    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return {"_unserialisable": str(value)[:1000]}


def runtime_for(bot_or_name: Any, **kwargs: Any) -> BotRuntime:
    """Convenience: build a runtime from a bot instance or spec name."""
    from aqp.bots.base import BaseBot, load_bot_from_spec

    bot = bot_or_name if isinstance(bot_or_name, BaseBot) else load_bot_from_spec(bot_or_name)
    return BotRuntime(bot, **kwargs)


__all__ = [
    "BotRunResult",
    "BotRuntime",
    "runtime_for",
]
