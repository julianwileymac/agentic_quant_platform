"""``AssistantRuntime`` — execute an :class:`AssistantSpec` end-to-end.

The Assistant Engine is a thin dispatcher over the existing AQP
runtimes — it never owns its own LLM tool loop, never imports ORM
models from agent / workflow code paths, and never publishes to Redis
directly. Every behaviour delegates to one of:

- :class:`aqp.agents.runtime.AgentRuntime` (mode=``agent``).
- :class:`aqp.agents.orchestration.runtime.WorkflowRuntime`
  (mode=``workflow``).

Telemetry contract:

- One :func:`aqp.tasks._progress.emit` frame at every transition; a
  single :func:`emit_done` frame on terminal status (rule 4).
- One ``AssistantRun`` ledger row + N ``AssistantRunEvent`` rows so
  the frontend timeline can reconstruct execution deterministically.
- Per-run halt: ``WorkflowRuntime`` already polls
  ``aqp:workflow:halt:<run_id>`` AND ``aqp:assistant:halt:<run_id>``
  (defect 3 fix). The assistant runtime publishes its run id to the
  same key so a single ``/assistants/halt`` mutation halts both the
  outer assistant and the dispatched inner runtime.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aqp.agents.observability import (
    assistant_message_span,
    assistant_run_span,
    workflow_handoff_span,
)
from aqp.assistants.spec import AssistantSpec
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "halted", "error", "rejected"}
)


class AssistantRuntime:
    """Execute one :class:`AssistantSpec` against an AQP runtime."""

    def __init__(
        self,
        spec: AssistantSpec,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        spec_version_id: str | None = None,
        context: Any | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        self.session_id = session_id
        self.spec_version_id = spec_version_id
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:  # pragma: no cover
                context = None
        self.context = context
        self._event_seq = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, prompt: str, inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Execute the spec end-to-end. Always returns a result dict.

        Errors never raise — they're captured into ``status="error"``
        so the caller can persist a partial trace and surface it in
        the UI. Mirrors :meth:`AgentRuntime.run` and
        :meth:`WorkflowRuntime.run` semantics.
        """
        start = time.perf_counter()
        merged_inputs: dict[str, Any] = dict(inputs or {})
        merged_inputs.setdefault("prompt", prompt)

        self._open_run(prompt=prompt, inputs=merged_inputs)
        with assistant_message_span(
            run_id=self.run_id,
            role="user",
            turn=1,
            session_id=self.session_id,
        ):
            self._persist_message(role="user", content=prompt, turn=1)
        self._emit("start", "Assistant run starting", spec=self.spec.name)

        try:
            if self._is_halted_at_start():
                return self._finalise(
                    status="halted",
                    output={},
                    error="halted before dispatch",
                    start=start,
                    halted=True,
                )
            with assistant_run_span(
                assistant_spec_name=self.spec.name,
                run_id=self.run_id,
                session_id=self.session_id,
                spec_version_id=self.spec_version_id,
                mode=self.spec.mode,
                target_ref=self.spec.target_ref,
            ):
                if self.spec.mode == "agent":
                    payload = self._dispatch_agent(prompt, merged_inputs)
                elif self.spec.mode == "workflow":
                    payload = self._dispatch_workflow(prompt, merged_inputs)
                else:  # pragma: no cover - validated by AssistantSpec
                    raise ValueError(f"unknown assistant mode {self.spec.mode!r}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("AssistantRuntime crashed for %s", self.spec.name)
            self._record_event(kind="error", name="dispatch_exception", error=str(exc))
            return self._finalise(
                status="error", output={}, error=str(exc), start=start
            )

        return self._finalise(
            status=payload.get("status", "completed"),
            output=payload.get("output", {}),
            error=payload.get("error"),
            cost_usd=float(payload.get("cost_usd", 0.0) or 0.0),
            n_calls=int(payload.get("n_calls", 0) or 0),
            n_tool_calls=int(payload.get("n_tool_calls", 0) or 0),
            n_rag_hits=int(payload.get("n_rag_hits", 0) or 0),
            target_run_kind=payload.get("target_run_kind"),
            target_run_id=payload.get("target_run_id"),
            start=start,
            halted=bool(payload.get("halted", False)),
        )

    # ------------------------------------------------------------------
    # Dispatchers
    # ------------------------------------------------------------------

    def _dispatch_agent(self, prompt: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
        from aqp.agents.registry import get_agent_spec
        from aqp.agents.runtime import AgentRuntime

        target_name = self.spec.agent_spec_name or ""
        if not target_name:
            raise ValueError("AssistantSpec(mode='agent') missing agent_spec_name")

        agent_spec = get_agent_spec(target_name)
        agent_spec = self._apply_tool_policy(agent_spec)
        self._emit(
            "dispatch",
            f"Dispatching to AgentRuntime[{target_name}]",
            target_kind="agent",
            target_ref=target_name,
        )
        self._record_event(
            kind="workflow_handoff",
            name="agent_runtime",
            attributes={"target": target_name},
        )

        with workflow_handoff_span(
            run_id=self.run_id,
            target_kind="agent",
            target_ref=target_name,
        ):
            runtime = AgentRuntime(
                spec=agent_spec,
                run_id=str(uuid.uuid4()),
                task_id=self.task_id,
                session_id=self.session_id,
                context=self.context,
            )
            result = runtime.run(inputs=dict(inputs))

        # ``AgentRunResult`` maps cleanly onto the typed payload the
        # finalise call expects; we keep the dict surface so workflow
        # dispatch can reuse the same shape.
        text = self._extract_text(getattr(result, "output", {}) or {})
        if text:
            self._persist_message(role="assistant", content=text, turn=2)

        return {
            "status": getattr(result, "status", "completed"),
            "output": getattr(result, "output", {}) or {},
            "error": getattr(result, "error", None),
            "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
            "n_calls": int(getattr(result, "n_calls", 0) or 0),
            "n_tool_calls": int(getattr(result, "n_tool_calls", 0) or 0),
            "n_rag_hits": int(getattr(result, "n_rag_hits", 0) or 0),
            "target_run_kind": "agent",
            "target_run_id": getattr(result, "run_id", None),
            "halted": getattr(result, "status", "") == "halted",
        }

    def _dispatch_workflow(
        self, prompt: str, inputs: Mapping[str, Any]
    ) -> dict[str, Any]:
        from aqp.agents.orchestration.registry_specs import (
            get_workflow_spec,
            persist_spec,
        )
        from aqp.agents.orchestration.runtime import WorkflowRuntime

        target_name = self.spec.workflow_spec_name or ""
        if not target_name:
            raise ValueError(
                "AssistantSpec(mode='workflow') missing workflow_spec_name"
            )

        workflow_spec = get_workflow_spec(target_name)
        spec_version_id = persist_spec(workflow_spec)
        self._emit(
            "dispatch",
            f"Dispatching to WorkflowRuntime[{target_name}]",
            target_kind="workflow",
            target_ref=target_name,
        )
        self._record_event(
            kind="workflow_handoff",
            name="workflow_runtime",
            attributes={"target": target_name},
        )

        with workflow_handoff_span(
            run_id=self.run_id,
            target_kind="workflow",
            target_ref=target_name,
        ):
            runtime = WorkflowRuntime(
                workflow_spec,
                run_id=str(uuid.uuid4()),
                task_id=self.task_id,
                session_id=self.session_id,
                context=self.context,
                spec_version_id=spec_version_id,
            )
            result = runtime.run(inputs=dict(inputs))

        # Synthesise a single ``assistant`` message from the workflow
        # output so the chat surface always has something to render.
        breadcrumbs = list(getattr(result, "breadcrumbs", []) or [])
        if breadcrumbs:
            summary = f"Workflow completed in {len(breadcrumbs)} adapter step(s)."
            self._persist_message(role="assistant", content=summary, turn=2)

        return {
            "status": getattr(result, "status", "completed"),
            "output": dict(getattr(result, "state", {}) or {}),
            "error": getattr(result, "error", None),
            "cost_usd": float(getattr(result, "cost_usd", 0.0) or 0.0),
            "n_calls": int(getattr(result, "n_calls", 0) or 0),
            "n_tool_calls": int(getattr(result, "n_tool_calls", 0) or 0),
            "n_rag_hits": int(getattr(result, "n_rag_hits", 0) or 0),
            "target_run_kind": "workflow",
            "target_run_id": getattr(result, "run_id", None),
            "halted": bool(getattr(result, "halted", False)),
        }

    # ------------------------------------------------------------------
    # Spec policy projection
    # ------------------------------------------------------------------

    def _apply_tool_policy(self, agent_spec: Any) -> Any:
        """Project ``AssistantToolPolicy`` onto the underlying ``AgentSpec``.

        Filters the spec's tools to ``allowed_tools`` (when non-empty),
        and merges ``explicit_scopes`` into every retained
        :class:`aqp.agents.spec.ToolRef`. Returns a copy — never
        mutates the registry-cached spec.
        """
        try:
            from aqp.agents.spec import AgentSpec
        except Exception:  # pragma: no cover - import always works
            return agent_spec
        if not isinstance(agent_spec, AgentSpec):
            return agent_spec

        policy = self.spec.tool_policy
        allowed = set(policy.allowed_tools or [])
        write_blocked = bool(policy.read_only) and "data:write" not in policy.explicit_scopes
        new_tools: list[Any] = []
        for ref in agent_spec.tools:
            if allowed and ref.name not in allowed:
                continue
            merged_scopes = list(dict.fromkeys([*ref.scopes, *policy.explicit_scopes]))
            if write_blocked and "data:write" in merged_scopes:
                merged_scopes.remove("data:write")
            new_tools.append(ref.model_copy(update={"scopes": merged_scopes}))

        return agent_spec.model_copy(update={"tools": new_tools})

    # ------------------------------------------------------------------
    # Halt
    # ------------------------------------------------------------------

    def _is_halted_at_start(self) -> bool:
        if self._redis_halt_set():
            return True
        return False

    def _redis_halt_set(self) -> bool:
        try:
            from aqp.config import settings as _settings

            redis_url = getattr(_settings, "redis_url", None)
            if not redis_url:
                return False
            import redis  # type: ignore[import-not-found]

            client = redis.Redis.from_url(redis_url, socket_timeout=0.25)
            return bool(client.exists(f"aqp:assistant:halt:{self.run_id}"))
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _open_run(self, *, prompt: str, inputs: Mapping[str, Any]) -> None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_assistants import AssistantRun

            with SessionLocal() as session:
                row = AssistantRun(
                    id=self.run_id,
                    assistant_spec_name=self.spec.name,
                    spec_version_id=self.spec_version_id,
                    session_id=self.session_id,
                    task_id=self.task_id,
                    status="running",
                    target_kind=self.spec.target_kind,
                    target_ref=self.spec.target_ref,
                    inputs=dict(inputs),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not open assistant_runs row", exc_info=True)

    def _persist_message(self, *, role: str, content: str, turn: int) -> None:
        if not self.session_id:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_assistants import AssistantMessage

            with SessionLocal() as session:
                row = AssistantMessage(
                    session_id=self.session_id,
                    run_id=self.run_id,
                    turn=turn,
                    role=role,
                    content=content,
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not persist assistant_message", exc_info=True)

    def _stamp_tenancy(self, row: Any) -> None:
        ctx = self.context
        if ctx is None:
            return
        for attr_ctx, attr_row in (
            ("user_id", "owner_user_id"),
            ("workspace_id", "workspace_id"),
            ("project_id", "project_id"),
            ("experiment_id", "experiment_id"),
            ("test_id", "test_id"),
        ):
            value = getattr(ctx, attr_ctx, None)
            if value and hasattr(row, attr_row) and getattr(row, attr_row, None) in (None, ""):
                setattr(row, attr_row, value)

    def _record_event(
        self,
        *,
        kind: str,
        name: str,
        attributes: Mapping[str, Any] | None = None,
        status: str | None = None,
        cost_usd: float | None = None,
        duration_ms: float | None = None,
        error: str | None = None,
    ) -> None:
        self._event_seq += 1
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_assistants import AssistantRunEvent

            with SessionLocal() as session:
                row = AssistantRunEvent(
                    run_id=self.run_id,
                    seq=self._event_seq,
                    kind=kind,
                    name=name,
                    attributes=dict(attributes or {}),
                    status=status,
                    cost_usd=cost_usd,
                    duration_ms=duration_ms,
                    error=error,
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not persist assistant_run_event", exc_info=True)

    def _finalise(
        self,
        *,
        status: str,
        output: Mapping[str, Any],
        error: str | None,
        start: float,
        cost_usd: float = 0.0,
        n_calls: int = 0,
        n_tool_calls: int = 0,
        n_rag_hits: int = 0,
        target_run_kind: str | None = None,
        target_run_id: str | None = None,
        halted: bool = False,
    ) -> dict[str, Any]:
        duration_ms = (time.perf_counter() - start) * 1000.0
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_assistants import AssistantRun

            with SessionLocal() as session:
                row = (
                    session.query(AssistantRun)
                    .filter(AssistantRun.id == self.run_id)
                    .one_or_none()
                )
                if row is not None:
                    row.status = status
                    row.output = dict(output or {})
                    row.error = error
                    row.cost_usd = float(cost_usd)
                    row.n_calls = int(n_calls)
                    row.n_tool_calls = int(n_tool_calls)
                    row.n_rag_hits = int(n_rag_hits)
                    row.duration_ms = float(round(duration_ms, 3))
                    row.completed_at = datetime.utcnow()
                    row.target_run_kind = target_run_kind
                    row.target_run_id = target_run_id
                    if halted or status == "halted":
                        row.halted = True
                        row.halted_at = datetime.utcnow()
                    session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not finalise assistant_runs row", exc_info=True)

        payload = {
            "run_id": self.run_id,
            "spec_name": self.spec.name,
            "status": status,
            "output": dict(output or {}),
            "error": error,
            "cost_usd": float(cost_usd),
            "n_calls": int(n_calls),
            "n_tool_calls": int(n_tool_calls),
            "n_rag_hits": int(n_rag_hits),
            "target_run_kind": target_run_kind,
            "target_run_id": target_run_id,
            "duration_ms": round(duration_ms, 3),
            "halted": bool(halted or status == "halted"),
        }
        if status in _TERMINAL_STATUSES and self.task_id:
            try:
                if status == "error" and error:
                    emit_error(self.task_id, error, **{"run_id": self.run_id})
                else:
                    emit_done(self.task_id, payload)
            except Exception:  # noqa: BLE001
                logger.debug("emit_done failed", exc_info=True)
        return payload

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, stage: str, message: str, **extras: Any) -> None:
        if not self.task_id:
            return
        try:
            emit(self.task_id, stage, message, run_id=self.run_id, **extras)
        except Exception:  # noqa: BLE001
            logger.debug("assistant progress emit failed", exc_info=True)

    @staticmethod
    def _extract_text(output: Mapping[str, Any]) -> str:
        if not output:
            return ""
        for key in ("text", "content", "message", "answer", "summary"):
            value = output.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""


def runtime_for(spec_name: str, **kwargs: Any) -> AssistantRuntime:
    """Convenience: look up a spec by name and build a runtime."""
    from aqp.assistants.registry import get_assistant_spec

    return AssistantRuntime(get_assistant_spec(spec_name), **kwargs)


__all__ = ["AssistantRuntime", "runtime_for"]
