"""MLSkillRuntime -- single sanctioned executor for MLSkill specs.

Mirrors :class:`aqp.agents.runtime.AgentRuntime` /
:class:`aqp.bots.runtime.BotRuntime` /
:class:`aqp_rl.runtime.RLRuntime` /
:class:`aqp.analysis.runtime.AnalysisRuntime`:

* Snapshots the spec into ``ml_skill_versions`` (idempotent by hash).
* Writes one ``ml_skill_runs`` row per :meth:`run` carrying
  ``experiment_id`` + ``test_id`` from the active
  :class:`RequestContext` (Hard Rule 34).
* Emits a single :class:`aqp.data.catalog.lineage.LineageEvent` so the
  lineage graph + the OpenLineage outbox observer see skill
  invocations.

The runtime composes registered :mod:`aqp_models.interfaces` over the
:mod:`aqp_models.handlers` and runs the OOD :class:`RuleRegistry`
before invoking each step. Step outputs flow through a shared
``ctx_payload`` dict so a regime classifier can hand its prediction
to a downstream regime-specialised predictor.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aqp_models.handlers.base import HandlerContext
from aqp_models.spec import MLSkillSpec

logger = logging.getLogger(__name__)


@dataclass
class SkillRunResult:
    """Outcome of one :meth:`MLSkillRuntime.run` call."""

    skill_name: str
    spec_version_id: str | None
    run_id: str | None
    status: str
    started_at: datetime
    completed_at: datetime | None
    elapsed_ms: float
    step_outputs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "spec_version_id": self.spec_version_id,
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "elapsed_ms": float(self.elapsed_ms),
            "step_outputs": list(self.step_outputs),
            "error": self.error,
        }


class MLSkillRuntime:
    """Single sanctioned entry point for executing an :class:`MLSkillSpec`."""

    def __init__(self, spec: MLSkillSpec) -> None:
        if not isinstance(spec, MLSkillSpec):
            raise TypeError(
                "MLSkillRuntime requires an MLSkillSpec instance, got "
                + type(spec).__name__
            )
        self.spec = spec
        self._spec_version_id: str | None = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def snapshot(self) -> str | None:
        """Persist the spec hash; idempotent."""
        if self._spec_version_id is not None:
            return self._spec_version_id
        try:
            from aqp_models.registry import persist_spec

            self._spec_version_id = persist_spec(self.spec)
        except Exception:  # noqa: BLE001
            logger.debug("snapshot failed for %s", self.spec.name, exc_info=True)
            self._spec_version_id = None
        return self._spec_version_id

    def run(
        self,
        *,
        inputs: dict[str, Any],
        ctx: HandlerContext | None = None,
        experiment_id: str | None = None,
        test_id: str | None = None,
    ) -> SkillRunResult:
        ctx = ctx or HandlerContext()
        started = datetime.utcnow()
        wall_start = time.monotonic()

        spec_version_id = self.snapshot()
        run_id = self._open_run_row(
            ctx=ctx,
            experiment_id=experiment_id,
            test_id=test_id,
            started=started,
            spec_version_id=spec_version_id,
        )

        step_outputs: list[dict[str, Any]] = []
        shared: dict[str, Any] = dict(inputs)
        status = "succeeded"
        error: str | None = None
        for step in self.spec.steps:
            step_started = time.monotonic()
            try:
                # Pre-step OOD rule check
                self._apply_rules(step=step, payload=shared, ctx=ctx)
                wrapper = self._build_step_wrapper(step)
                output, descriptor = self._invoke_step(wrapper, step=step, shared=shared)
                step_outputs.append(
                    {
                        "step": step.name,
                        "interface_kind": step.interface_kind,
                        "elapsed_ms": _ms(step_started),
                        "descriptor": descriptor,
                    }
                )
                if step.output_alias:
                    shared[step.output_alias] = output
                shared.setdefault("__steps__", []).append(
                    {"name": step.name, "kind": step.interface_kind, "output": _summarise(output)}
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("MLSkillRuntime step %s failed", step.name)
                step_outputs.append(
                    {
                        "step": step.name,
                        "interface_kind": step.interface_kind,
                        "elapsed_ms": _ms(step_started),
                        "error": str(exc),
                    }
                )
                status = "failed"
                error = str(exc)
                break

        completed = datetime.utcnow()
        elapsed_ms = round((time.monotonic() - wall_start) * 1000.0, 3)
        self._close_run_row(
            run_id=run_id,
            status=status,
            completed_at=completed,
            error=error,
            elapsed_ms=elapsed_ms,
            step_outputs=step_outputs,
        )
        self._emit_lineage(
            ctx=ctx,
            status=status,
            elapsed_ms=elapsed_ms,
            spec_version_id=spec_version_id,
            run_id=run_id,
        )

        return SkillRunResult(
            skill_name=self.spec.name,
            spec_version_id=spec_version_id,
            run_id=run_id,
            status=status,
            started_at=started,
            completed_at=completed,
            elapsed_ms=elapsed_ms,
            step_outputs=step_outputs,
            error=error,
        )

    # ------------------------------------------------------------------
    # Step invocation
    # ------------------------------------------------------------------

    def _apply_rules(
        self,
        *,
        step: Any,
        payload: dict[str, Any],
        ctx: HandlerContext,
    ) -> None:
        try:
            from aqp_models.rules import RuleRegistry
        except Exception:  # noqa: BLE001
            return
        rules = RuleRegistry.load_pack(self.spec.guardrails.rule_pack)
        for rule in rules:
            verdict = rule.evaluate(payload=payload, step=step, ctx=ctx)
            if not verdict.allowed:
                raise RuntimeError(
                    f"rule {rule.name!r} rejected step {step.name!r}: {verdict.reason}"
                )

    def _build_step_wrapper(self, step: Any) -> Any:
        from aqp.core.registry import build_from_config
        from aqp_models.interfaces import wrap_model

        # Resolve the underlying model object.
        if "." in step.model_ref:
            module_path, cls_name = step.model_ref.rsplit(".", 1)
            cfg = {"class": cls_name, "module_path": module_path, "kwargs": dict(step.kwargs)}
        else:
            cfg = {"class": step.model_ref, "kwargs": dict(step.kwargs)}
        model = build_from_config(cfg)
        # Wrap in the requested interface.
        return wrap_model(model, kind=step.interface_kind, alias=step.name)

    def _invoke_step(
        self, wrapper: Any, *, step: Any, shared: dict[str, Any]
    ) -> tuple[Any, dict[str, Any]]:
        kind = step.interface_kind
        if kind == "predictor":
            result = wrapper.predict(shared.get("features") or shared.get("X") or shared)
            return result, result.to_json() if hasattr(result, "to_json") else {"value": str(result)}
        if kind == "forecaster":
            history = shared.get("history") or shared.get("series") or []
            horizon = int(shared.get("horizon", 5))
            result = wrapper.forecast(history, horizon=horizon)
            return result, result.to_json()
        if kind == "classifier":
            result = wrapper.classify(shared.get("features") or shared.get("X") or shared)
            return result, result.to_json()
        if kind == "segmenter":
            series = shared.get("series") or shared.get("history") or []
            boundaries, metadata = wrapper.segment(series)
            return boundaries, {
                "boundaries": [b.to_json() for b in boundaries],
                "metadata": metadata.to_json(),
            }
        if kind == "analyzer":
            data = shared.get("text") or shared.get("documents") or shared
            result = wrapper.analyze(data)
            return result, result.to_json()
        raise RuntimeError(f"unsupported interface_kind {kind!r}")

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _open_run_row(
        self,
        *,
        ctx: HandlerContext,
        experiment_id: str | None,
        test_id: str | None,
        started: datetime,
        spec_version_id: str | None,
    ) -> str | None:
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_mlops import MlSkillRun

            with get_session() as session:
                row = MlSkillRun(
                    skill_name=self.spec.name,
                    skill_spec_version_id=spec_version_id,
                    status="running",
                    started_at=started,
                    experiment_id=experiment_id,
                    test_id=test_id,
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    owner_user_id=(ctx.actor if ctx.actor_kind == "user" else None),
                    actor=ctx.actor,
                    actor_kind=ctx.actor_kind,
                )
                session.add(row)
                session.flush()
                return row.id
        except Exception:  # noqa: BLE001
            logger.debug("ml_skill_runs open row failed", exc_info=True)
            return None

    def _close_run_row(
        self,
        *,
        run_id: str | None,
        status: str,
        completed_at: datetime,
        error: str | None,
        elapsed_ms: float,
        step_outputs: list[dict[str, Any]],
    ) -> None:
        if not run_id:
            return
        try:
            from aqp.persistence.db import get_session
            from aqp.persistence.models_mlops import MlSkillRun

            with get_session() as session:
                row = session.get(MlSkillRun, run_id)
                if row is None:
                    return
                row.status = status
                row.completed_at = completed_at
                row.elapsed_ms = float(elapsed_ms)
                row.error = error
                row.step_outputs = list(step_outputs)
        except Exception:  # noqa: BLE001
            logger.debug("ml_skill_runs close failed", exc_info=True)

    def _emit_lineage(
        self,
        *,
        ctx: HandlerContext,
        status: str,
        elapsed_ms: float,
        spec_version_id: str | None,
        run_id: str | None,
    ) -> None:
        try:
            from aqp.data.catalog.lineage import LineageEvent, get_lineage_bus

            get_lineage_bus().emit(
                LineageEvent(
                    transform_kind="ml_skill",
                    actor=ctx.actor or "mlops",
                    actor_kind=ctx.actor_kind or "system",
                    mcp_tool_name=self.spec.name,
                    service_name="aqp_models.runtime",
                    summary=f"skill {self.spec.name} {status}",
                    workspace_id=ctx.workspace_id,
                    project_id=ctx.project_id,
                    details={
                        "spec_version_id": spec_version_id,
                        "run_id": run_id,
                        "status": status,
                        "elapsed_ms": elapsed_ms,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            logger.debug("lineage emit failed for MLSkillRuntime", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms(started: float) -> float:
    return round((time.monotonic() - started) * 1000.0, 3)


def _summarise(value: Any) -> Any:
    """Lossy summary used inside ``__steps__`` so downstream steps can branch."""
    if hasattr(value, "to_json"):
        try:
            payload = value.to_json()
            return _shrink(payload)
        except Exception:  # noqa: BLE001
            return repr(value)
    return _shrink(value)


def _shrink(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _shrink(v) for k, v in value.items()}
    if isinstance(value, list):
        if len(value) > 32:
            return value[:8] + ["... truncated ..."] + value[-4:]
        return [_shrink(v) for v in value]
    return value


__all__ = ["MLSkillRuntime", "SkillRunResult"]
