"""``LabRuntime`` — the single sanctioned executor for a Data Lab GraphSpec.

Mirrors the shape of :class:`aqp.analysis.runtime.AnalysisRuntime` and
:class:`aqp.agents.orchestration.runtime.WorkflowRuntime`:

1. Run pre-flight AGENTS-rule compliance checks (raises on blocking
   violations).
2. Open a ``lab_runs`` row with ``status='running'``.
3. Compile the GraphSpec via the mode-specific compiler.
4. Dispatch — inline for Phase 0 single-process testing; Celery /
   Dagster for Phase 2+ once the wrappers ship.
5. Stream progress via :func:`aqp.tasks._progress.emit` so the WS
   gateway picks the frames up unchanged (AGENTS rule 4 frame shape).
6. Finalise the row + return a :class:`LabRunResult`.

The runtime never imports ORM models from agent paths, never calls
``router_complete`` directly, never writes Iceberg outside the
sanctioned wrapper, and never publishes to Redis from task code.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from aqp.lab.compiler import CompileContext, CompileResult, select_compiler
from aqp.lab.compliance import ComplianceError, check_graph_compliance
from aqp.lab.executors._types import NodeContext, NodeResult
from aqp.lab.hashing import compute_content_hash, snapshot_data_locator
from aqp.lab.registry import resolve_executor
from aqp.lab.schema import GraphSpec
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


@dataclass
class NodeOutcome:
    node_id: str
    node_type: str
    status: str
    metrics: dict[str, Any] = field(default_factory=dict)
    output_locator: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


@dataclass
class LabRunResult:
    run_id: str
    graph_content_hash: str
    mode: str
    status: str  # pending | running | done | error | halted | cancelled
    started_at: float
    duration_ms: float = 0.0
    breadcrumbs: list[dict[str, Any]] = field(default_factory=list)
    node_outcomes: list[NodeOutcome] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    task_id: str | None = None
    compile_target: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        return out


class LabRuntime:
    """Single executor for a GraphSpec across all four modes."""

    def __init__(
        self,
        spec: GraphSpec,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        lab_id: str | None = None,
        graph_id: str | None = None,
        context: Any | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        self.session_id = session_id
        self.lab_id = lab_id
        self.graph_id = graph_id
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:  # pragma: no cover - always importable in prod
                context = None
        self.context = context

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_run(self) -> LabRunResult:
        """Execute the GraphSpec end-to-end.

        Errors never raise — they are folded into ``LabRunResult.status``
        so the caller can persist a partial trace and surface it in the
        UI. This mirrors :meth:`AnalysisRuntime.run` and
        :meth:`WorkflowRuntime.run` semantics.
        """
        start = time.perf_counter()
        content_hash = self.spec.snapshot_hash()
        data_snapshot = snapshot_data_locator(self.spec)
        outcome_template = LabRunResult(
            run_id=self.run_id,
            graph_content_hash=content_hash,
            mode=self.spec.mode,
            status="running",
            started_at=time.time(),
            task_id=self.task_id,
        )
        run_db_id = self._open_run_row(content_hash, data_snapshot)

        self._emit("start", f"Lab run starting (mode={self.spec.mode})", spec_name=self.spec.name)

        # 1) Pre-flight compliance
        try:
            violations = check_graph_compliance(self.spec)
            blocking = [v for v in violations if v.severity == "error"]
            if blocking:
                raise ComplianceError(blocking)
        except ComplianceError as exc:
            return self._finalise(
                outcome_template,
                run_db_id=run_db_id,
                status="error",
                error=str(exc),
                start=start,
                breadcrumbs=[{"stage": "compliance", "violations": len(exc.violations)}],
            )

        # 2) Compile
        try:
            compiler = select_compiler(self.spec.mode)
            compile_ctx = CompileContext(
                run_id=self.run_id,
                task_id=self.task_id,
                session_id=self.session_id,
                lab_id=self.lab_id,
                request_context=self.context,
            )
            compile_result = compiler(self.spec, compile_ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("compile failed for mode %s", self.spec.mode)
            return self._finalise(
                outcome_template,
                run_db_id=run_db_id,
                status="error",
                error=f"compile failed: {exc}",
                start=start,
            )

        self._emit(
            "compiled",
            f"compiled to target={compile_result.target}",
            target=compile_result.target,
        )

        # 3) Dispatch — Phase 0 only handles inline + the inline-canvas
        # path. Phase 2 swaps celery_canvas / celery_group / dagster_job
        # to their real backends.
        try:
            outcomes, metrics = self._dispatch(compile_result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("dispatch failed")
            return self._finalise(
                outcome_template,
                run_db_id=run_db_id,
                status="error",
                error=f"dispatch failed: {exc}",
                start=start,
                breadcrumbs=list(compile_result.breadcrumbs),
            )

        node_error = next((o for o in outcomes if o.status == "error"), None)
        status = "error" if node_error else "done"
        error = node_error.error if node_error else None

        return self._finalise(
            outcome_template,
            run_db_id=run_db_id,
            status=status,
            error=error,
            start=start,
            breadcrumbs=list(compile_result.breadcrumbs),
            node_outcomes=outcomes,
            metrics=metrics,
            compile_target=compile_result.target,
        )

    # ------------------------------------------------------------------
    # Dispatchers
    # ------------------------------------------------------------------

    def _dispatch(
        self, compile_result: CompileResult
    ) -> tuple[list[NodeOutcome], dict[str, Any]]:
        target = compile_result.target
        if target == "inline":
            return self._dispatch_inline_eda(compile_result.payload)
        if target == "celery_canvas":
            # Phase 0 walks the canvas inline; Phase 2 swaps in
            # celery.canvas.chain / chord against ``run_lab_node``.
            return self._dispatch_inline_canvas(compile_result.payload)
        if target == "celery_group":
            return self._dispatch_sweep_stub(compile_result.payload)
        if target == "dagster_job":
            return self._dispatch_simulation_stub(compile_result.payload)
        raise ValueError(f"unknown compile target: {target!r}")

    def _dispatch_inline_eda(
        self, payload: dict[str, Any]
    ) -> tuple[list[NodeOutcome], dict[str, Any]]:
        # Phase 0: just record the cells we received; full reactive
        # execution lands in Phase 1.
        cells = payload.get("cells", [])
        outcomes: list[NodeOutcome] = []
        for cell in cells:
            outcomes.append(
                NodeOutcome(
                    node_id=cell.get("id", ""),
                    node_type=f"eda.cell.{cell.get('kind', 'python')}",
                    status="done",
                    output_locator={"kind": "eda_cell_pending", "id": cell.get("id")},
                )
            )
        return outcomes, {"n_cells": len(cells)}

    def _dispatch_inline_canvas(
        self, payload: dict[str, Any]
    ) -> tuple[list[NodeOutcome], dict[str, Any]]:
        plan = payload.get("plan", [])
        outcomes: list[NodeOutcome] = []
        # Per-node ``NodeContext`` accumulator. We mutate ``extras`` so
        # in-process executors can pass Arrow tables forward without
        # round-tripping through MinIO (Phase 0 only).
        shared_extras: dict[str, Any] = {}
        node_locators: dict[str, dict[str, Any]] = {}

        spec_nodes = {n.id: n for n in self.spec.nodes}
        for plan_step in plan:
            node_id = plan_step["node_id"]
            node = spec_nodes.get(node_id)
            if node is None:
                outcomes.append(
                    NodeOutcome(
                        node_id=node_id,
                        node_type=plan_step.get("node_type", ""),
                        status="error",
                        error=f"plan references unknown node id {node_id!r}",
                    )
                )
                continue

            node_start = time.perf_counter()
            self._emit(
                "node:start",
                f"node {node_id} ({node.type}) started",
                node_id=node_id,
                node_type=node.type,
            )

            # Resolve upstream locators from the in-memory map.
            upstream: dict[str, Any] = {}
            wiring = plan_step.get("wiring", {})
            for port_name, (src_id, _src_port) in wiring.items():
                upstream_locator = node_locators.get(src_id, {})
                # Stamp node_id on the locator so downstream
                # executors can find the Arrow blob in ``_arrow_outputs``.
                upstream[port_name] = {**upstream_locator, "node_id": src_id}

            node_ctx = NodeContext(
                run_id=self.run_id,
                node_id=node_id,
                node_type=node.type,
                upstream=upstream,
                task_id=self.task_id,
                request_context=self.context,
                extras=shared_extras,
            )

            try:
                executor = resolve_executor(node.type)
                result: NodeResult = executor(node, node_ctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("node %s (%s) executor crashed", node_id, node.type)
                result = NodeResult(
                    status="error",
                    error=f"executor crashed: {exc}",
                    log_label=f"crash:{node.type}",
                )

            duration_ms = (time.perf_counter() - node_start) * 1000.0
            node_locators[node_id] = result.output_locator
            outcomes.append(
                NodeOutcome(
                    node_id=node_id,
                    node_type=node.type,
                    status=result.status,
                    metrics=dict(result.metrics or {}),
                    output_locator=dict(result.output_locator or {}),
                    error=result.error,
                    duration_ms=duration_ms,
                )
            )
            self._record_node_run_row(node_id, node.type, result, duration_ms)

            stage = "node:done" if result.status == "done" else f"node:{result.status}"
            self._emit(
                stage,
                f"node {node_id} {result.status}",
                node_id=node_id,
                node_type=node.type,
                duration_ms=round(duration_ms, 3),
                metrics=result.metrics,
            )

            if result.status == "error":
                # Halt on first error to mirror typical Celery canvas
                # semantics; downstream nodes stay status=pending.
                break

        return outcomes, {"n_executed": len(outcomes)}

    def _dispatch_sweep_stub(
        self, payload: dict[str, Any]
    ) -> tuple[list[NodeOutcome], dict[str, Any]]:
        """Execute the planned sweep inline via :func:`execute_sweep_inline`.

        Each trial runs the same GraphSpec under the sweep's per-trial
        parameter overrides, captured into a single :class:`NodeOutcome`
        per trial (so the run-history drawer can still render lanes).
        The aggregate DSR + winner sit on the run's ``metrics`` dict and
        on ``LabRun.total_trials_searched`` so the Phase 3 honest-
        accounting contract holds.
        """
        from aqp.lab.evaluation.sweep_controller import execute_sweep_inline

        def _inline_runner(per_trial_spec: Any) -> dict[str, Any]:
            from aqp.lab.compiler import CompileContext
            from aqp.lab.compiler.testing import compile_testing

            ctx = CompileContext(
                run_id=self.run_id,
                task_id=self.task_id,
                session_id=self.session_id,
                lab_id=self.lab_id,
                request_context=self.context,
            )
            sub_compile = compile_testing(per_trial_spec, ctx)
            outcomes, metrics = self._dispatch_inline_canvas(sub_compile.payload)
            # Aggregate the trial's per-node metrics into one dict the
            # sweep controller can rank by primary_metric.
            agg: dict[str, Any] = dict(metrics or {})
            for outcome in outcomes:
                for k, v in (outcome.metrics or {}).items():
                    agg.setdefault(str(k), v)
            return agg

        try:
            sweep_result = execute_sweep_inline(
                self.spec,
                inline_runner=_inline_runner,
                parent_run_id=self.run_id,
                use_mlflow=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("sweep dispatch failed")
            return [], {"sweep_error": str(exc), "phase": "3"}

        # Persist total_trials_searched on the parent run so DSR is
        # computable post-hoc (rule per the plan §13 honest-tracking).
        self._update_run_total_trials(sweep_result.plan.total_trials_searched)

        outcomes: list[NodeOutcome] = []
        for trial in sweep_result.trials:
            outcomes.append(
                NodeOutcome(
                    node_id=f"trial-{trial.trial_id}",
                    node_type="lab.sweep_trial",
                    status=trial.status,
                    metrics=dict(trial.metrics),
                    output_locator={
                        "kind": "sweep_trial",
                        "trial_id": trial.trial_id,
                        "params": trial.params,
                        "primary_metric": trial.primary_metric,
                    },
                    error=trial.error,
                    duration_ms=trial.duration_ms,
                )
            )
        aggregate = {
            "n_trials_planned": int(sweep_result.plan.controller.total_planned),
            "n_trials_run": len(sweep_result.trials),
            "total_trials_searched": int(sweep_result.plan.total_trials_searched),
            "primary_metric": sweep_result.plan.primary_metric,
            "best_trial_id": sweep_result.best_trial_id,
            "best_metric": sweep_result.best_metric,
            "deflated_sharpe": sweep_result.deflated_sharpe,
            "cv": "combinatorial_purged" if sweep_result.plan.cv_paths else "holdout",
            "n_cv_paths": len(sweep_result.plan.cv_paths or []),
        }
        return outcomes, aggregate

    def _update_run_total_trials(self, total: int) -> None:
        """Stamp the parent run's honest ``total_trials_searched`` count."""
        if not self.graph_id:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_lab import LabRun

            with SessionLocal() as session:
                row = session.get(LabRun, self.run_id)
                if row is not None:
                    row.total_trials_searched = int(max(1, total))
                    session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("could not stamp total_trials_searched", exc_info=True)

    def _dispatch_simulation_stub(
        self, payload: dict[str, Any]
    ) -> tuple[list[NodeOutcome], dict[str, Any]]:
        """Submit the simulation through the Dagster sandbox bridge.

        Phase 4 — :func:`aqp.lab.executors._dagster_bridge.submit_simulation`
        packages the GraphSpec + SimulationConfig into a SandboxRuntime
        job spec (rule 32 isolation) when Dagster is reachable, and
        falls back to a synchronous inline run for the sub-mode runner
        when it isn't. Either path returns a structured summary the
        Simulation panel can render.
        """
        from aqp.lab.executors._dagster_bridge import submit_simulation
        from aqp.lab.schema import SimulationConfig

        sim_cfg = self.spec.mode_config.simulation
        if sim_cfg is None:
            # Defaults already applied by the compliance + compiler
            # layers; build a SimulationConfig() so the bridge has a
            # consistent argument shape.
            sim_cfg = SimulationConfig()

        try:
            handle, summary = submit_simulation(
                self.spec,
                sim_cfg,
                session_id=self.session_id,
                task_id=self.task_id,
                run_id=self.run_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("simulation dispatch failed")
            return [], {"sim_error": str(exc), "env": sim_cfg.env}

        # Persist the dagster_run_id onto the parent LabRun row so the
        # Simulation panel can follow up + so the data.lab.* MCP tool
        # surfaces a stable handle to the running job.
        self._update_run_dagster_id(handle.dagster_run_id)
        outcomes: list[NodeOutcome] = [
            NodeOutcome(
                node_id=f"sim:{handle.env}",
                node_type="lab.simulation",
                status=summary.get("status", "done") or "done",
                metrics=summary.get("summary") if isinstance(summary.get("summary"), dict) else summary,
                output_locator={
                    "kind": "simulation",
                    "env": handle.env,
                    "dagster_run_id": handle.dagster_run_id,
                    "sandbox_session_id": handle.sandbox_session_id,
                    "inline_fallback": handle.inline_fallback,
                },
                error=summary.get("error") if summary.get("status") == "error" else None,
                duration_ms=float(summary.get("duration_ms") or 0.0),
            )
        ]
        return outcomes, {
            "env": handle.env,
            "dagster_run_id": handle.dagster_run_id,
            "inline_fallback": handle.inline_fallback,
            "duration_ms": summary.get("duration_ms"),
            "summary": summary,
        }

    def _update_run_dagster_id(self, dagster_run_id: str) -> None:
        if not self.graph_id:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_lab import LabRun

            with SessionLocal() as session:
                row = session.get(LabRun, self.run_id)
                if row is not None:
                    row.dagster_run_id = dagster_run_id
                    session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("could not stamp dagster_run_id", exc_info=True)

    # ------------------------------------------------------------------
    # EDA single-cell preview
    # ------------------------------------------------------------------

    def preview_cell(self, code: str, cell_id: str | None = None) -> dict[str, Any]:
        """Synchronously preview a single EDA Python cell.

        Routes through the per-session :class:`EdaKernel` (Phase 1).
        Each ``session_id`` owns one long-lived Python namespace +
        reactive cell DAG; the kernel executes the cell inside a
        bounded AST safety guard, captures stdout/stderr/repr, and
        returns the deterministic stale-descendant list so the UI
        can mark downstream cells stale.
        """
        cid = cell_id or f"c-{uuid.uuid4().hex[:8]}"
        try:
            from aqp.lab.eda.kernel import default_kernel_registry

            kernel = default_kernel_registry().get_or_create(
                self.session_id or self.run_id
            )
            result = kernel.execute_cell(cid, code)
        except Exception as exc:  # noqa: BLE001 - never crash the WS frame
            logger.exception("EDA preview_cell crashed")
            return {
                "cell_id": cid,
                "status": "error",
                "error": str(exc),
                "stale_ids": [],
                "render": {"kind": "kernel_unavailable"},
                "code_size": len(code or ""),
            }

        return {
            "cell_id": cid,
            "status": result.status,
            "stale_ids": list(result.stale_ids),
            "render": dict(result.render),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "repr": result.repr_value,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _open_run_row(
        self, content_hash: str, data_snapshot: dict[str, Any]
    ) -> str | None:
        if self.graph_id is None:
            return None
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_lab import LabRun

            with SessionLocal() as session:
                row = LabRun(
                    id=self.run_id,
                    graph_id=self.graph_id,
                    lab_id=self.lab_id,
                    mode=self.spec.mode,
                    status="running",
                    session_id=self.session_id,
                    task_id=self.task_id,
                    content_hash=content_hash,
                    data_snapshot=dict(data_snapshot or {}),
                    started_at=datetime.utcnow(),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
                return row.id
        except Exception:  # noqa: BLE001 - never block run on DB unavailability
            logger.debug("Could not open lab_runs row", exc_info=True)
            return None

    def _record_node_run_row(
        self,
        node_id: str,
        node_type: str,
        result: NodeResult,
        duration_ms: float,
    ) -> None:
        if self.graph_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_lab import LabNodeRun

            with SessionLocal() as session:
                row = LabNodeRun(
                    run_id=self.run_id,
                    node_id=node_id,
                    node_type=node_type,
                    status=result.status,
                    output_locator=dict(result.output_locator or {}),
                    metrics=dict(result.metrics or {}),
                    error=result.error,
                    log_label=result.log_label,
                    duration_ms=float(duration_ms),
                    started_at=datetime.utcnow(),
                    ended_at=datetime.utcnow(),
                )
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("Could not record lab_node_runs row", exc_info=True)

    def _finalise(
        self,
        result: LabRunResult,
        *,
        run_db_id: str | None,
        status: str,
        error: str | None,
        start: float,
        breadcrumbs: list[dict[str, Any]] | None = None,
        node_outcomes: list[NodeOutcome] | None = None,
        metrics: dict[str, Any] | None = None,
        compile_target: str | None = None,
    ) -> LabRunResult:
        duration_ms = (time.perf_counter() - start) * 1000.0
        result.status = status
        result.error = error
        result.duration_ms = duration_ms
        if breadcrumbs is not None:
            result.breadcrumbs = list(breadcrumbs)
        if node_outcomes is not None:
            result.node_outcomes = list(node_outcomes)
        if metrics is not None:
            result.metrics = dict(metrics)
        if compile_target is not None:
            result.compile_target = compile_target

        if run_db_id is not None:
            try:
                from aqp.persistence.db import SessionLocal
                from aqp.persistence.models_lab import LabRun

                with SessionLocal() as session:
                    row = session.get(LabRun, run_db_id)
                    if row is not None:
                        row.status = status
                        row.error = error
                        row.metrics = dict(result.metrics)
                        row.result_summary = {
                            "n_outcomes": len(result.node_outcomes),
                            "n_errors": sum(
                                1 for o in result.node_outcomes if o.status == "error"
                            ),
                            "compile_target": compile_target,
                        }
                        row.duration_ms = float(round(duration_ms, 3))
                        row.ended_at = datetime.utcnow()
                        session.commit()
            except Exception:  # noqa: BLE001
                logger.debug("Could not finalise lab_runs row", exc_info=True)

        payload = result.to_dict()
        if status in {"done", "halted", "cancelled"} and self.task_id:
            try:
                emit_done(self.task_id, payload, context=self.context)
            except Exception:  # noqa: BLE001
                logger.debug("emit_done failed", exc_info=True)
        elif status == "error" and self.task_id:
            try:
                emit_error(self.task_id, error or "unknown lab error", context=self.context)
            except Exception:  # noqa: BLE001
                logger.debug("emit_error failed", exc_info=True)

        return result

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _emit(self, stage: str, message: str, **extras: Any) -> None:
        if not self.task_id:
            return
        try:
            emit(
                self.task_id,
                stage,
                message,
                run_id=self.run_id,
                graph_content_hash=self.spec.snapshot_hash(),
                **extras,
            )
        except Exception:  # noqa: BLE001
            logger.debug("lab progress emit failed", exc_info=True)


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------


def runtime_for_spec(spec: GraphSpec, **kwargs: Any) -> LabRuntime:
    return LabRuntime(spec, **kwargs)


def runtime_for_graph_id(graph_id: str, **kwargs: Any) -> LabRuntime:
    """Load a persisted ``lab_graphs`` row and instantiate the runtime."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabGraph
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("persistence layer unavailable") from exc

    with SessionLocal() as session:
        row = session.get(LabGraph, graph_id)
        if row is None:
            raise KeyError(f"LabGraph {graph_id!r} not found")
        spec = GraphSpec.model_validate(row.spec)
    return LabRuntime(spec, graph_id=graph_id, **kwargs)


__all__ = [
    "LabRunResult",
    "LabRuntime",
    "NodeOutcome",
    "runtime_for_graph_id",
    "runtime_for_spec",
]
