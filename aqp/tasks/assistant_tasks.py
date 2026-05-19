"""Celery task for the Assistant Engine (Phase 3).

Single thin wrapper around :class:`aqp.assistants.runtime.AssistantRuntime`,
mirroring :mod:`aqp.tasks.orchestration_tasks`:

- pass IDs only (rule 5), re-fetching the spec inside the worker;
- emit progress through :func:`aqp.tasks._progress.emit` /
  :func:`emit_done` / :func:`emit_error` (rule 4);
- never import ORM models at module top-level (matches the
  agent / workflow / paper task patterns);
- never call ``router_complete`` directly — the dispatched
  :class:`AgentRuntime` / :class:`WorkflowRuntime` owns the LLM tool
  loop.

Halt semantics: when ``settings.assistant_engine_enabled`` is off the
task surfaces a clean ``emit_error`` instead of crashing the worker;
when the per-run Redis halt flag (``aqp:assistant:halt:<run_id>``) or
the linked ``WorkflowRun`` halt flag is set, the runtime exits early
with ``status="halted"``.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app
from aqp.tasks.secure_task import SecureTask

logger = logging.getLogger(__name__)


def _bind_request_context(payload: dict[str, Any] | None) -> Any | None:
    """Rebuild a :class:`RequestContext` inside the worker from kwargs.

    The route serialises via ``ctx.to_dict()`` and the task body
    rehydrates here so tenancy / experiment / project FKs round-trip
    onto every persisted ledger row (rule 5). ``RequestContext`` is a
    plain dataclass so we round-trip through the dict-keyed kwargs;
    unknown keys are dropped to keep the bind defensive.
    """
    if not payload:
        return None
    try:
        from aqp.auth.context import RequestContext

        from dataclasses import fields

        allowed = {f.name for f in fields(RequestContext)}
        kwargs = {k: v for k, v in payload.items() if k in allowed}
        kwargs.setdefault("user_id", "agent_runtime")
        return RequestContext(**kwargs)
    except Exception:  # noqa: BLE001
        logger.debug("RequestContext rehydrate failed", exc_info=True)
        return None


def _run_assistant_impl(
    task_id: str,
    *,
    assistant_spec_name: str,
    spec_version_id: str | None = None,
    session_id: str | None = None,
    prompt: str = "",
    inputs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Underlying implementation — testable without Celery binding.

    The Celery wrapper :func:`run_assistant` is a 3-line shim that
    forwards ``self.request.id`` here, so unit tests can exercise the
    body without monkeypatching the ``bind=True`` descriptor.
    """
    emit(
        task_id,
        "start",
        "Starting assistant",
        spec=assistant_spec_name,
        spec_version_id=spec_version_id,
    )

    bound_context = _bind_request_context(context)

    try:
        spec = _resolve_spec(
            spec_version_id=spec_version_id,
            spec_name=assistant_spec_name,
        )
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"spec resolution failed: {exc}")
        raise

    if spec is None:
        msg = (
            "no spec resolvable from spec_version_id "
            f"{spec_version_id!r} / assistant_spec_name {assistant_spec_name!r}"
        )
        emit_error(task_id, msg)
        return {"ok": False, "error": msg}

    from aqp.assistants.runtime import AssistantRuntime

    runtime = AssistantRuntime(
        spec,
        task_id=task_id,
        session_id=session_id,
        spec_version_id=spec_version_id,
        context=bound_context,
    )
    emit(
        task_id,
        "running",
        "Dispatching assistant runtime",
        mode=spec.mode,
        target_ref=spec.target_ref,
    )
    try:
        payload = runtime.run(prompt=prompt, inputs=inputs or {})
    except Exception as exc:  # noqa: BLE001
        logger.exception("assistant_tasks.run_assistant crashed")
        emit_error(task_id, str(exc))
        raise

    # ``AssistantRuntime.run`` already publishes the terminal
    # ``emit_done`` frame; we still return the payload so Celery's
    # result store sees the dict.
    return payload


@celery_app.task(bind=True, base=SecureTask, name="aqp.tasks.assistant_tasks.run_assistant")
def run_assistant(
    self,
    *,
    assistant_spec_name: str,
    spec_version_id: str | None = None,
    session_id: str | None = None,
    prompt: str = "",
    inputs: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Materialise + execute one :class:`AssistantSpec`.

    Resolves the spec in order:

    1. If ``spec_version_id`` is provided AND
       ``settings.assistant_engine_versioning_enabled`` is on, hydrate
       the frozen payload (deterministic replay).
    2. Otherwise look the spec up by ``assistant_spec_name`` in the
       in-memory registry shipped by :mod:`aqp.assistants.registry`.
    3. If neither lookup succeeds, emit a clean error frame and return.
    """
    task_id = self.request.id or "local"
    return _run_assistant_impl(
        task_id,
        assistant_spec_name=assistant_spec_name,
        spec_version_id=spec_version_id,
        session_id=session_id,
        prompt=prompt,
        inputs=inputs,
        context=context,
    )


def _resolve_spec(
    *,
    spec_version_id: str | None,
    spec_name: str | None,
) -> Any | None:
    """Hydrate an :class:`AssistantSpec` from version id or in-memory registry."""
    if spec_version_id:
        try:
            from aqp.assistants.registry import replay_spec_version

            return replay_spec_version(spec_version_id)
        except Exception:  # noqa: BLE001
            logger.debug(
                "assistant spec version replay failed; falling back to spec_name lookup",
                exc_info=True,
            )

    if spec_name:
        try:
            from aqp.assistants.registry import get_assistant_spec

            return get_assistant_spec(spec_name)
        except KeyError:
            return None
        except Exception:  # noqa: BLE001
            logger.debug(
                "assistant spec registry get_assistant_spec missing", exc_info=True
            )

    return None


__all__ = ["_resolve_spec", "_run_assistant_impl", "run_assistant"]
