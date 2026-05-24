"""Data Lab Celery tasks.

Two thin wrappers over :class:`aqp.lab.runtime.LabRuntime`:

- :func:`run_lab_graph` — the route-side entry point. Mirrors the
  ``aqp.tasks.analysis_flow_tasks.*`` pattern: load the persisted
  ``lab_graphs`` row, instantiate the runtime, call
  :meth:`LabRuntime.submit_run`, emit canonical progress, return.
- :func:`run_lab_node` — Phase 2 hand-off that the Testing-mode
  ``celery.canvas.chain`` will dispatch one task per node. For
  Phase 0 the runtime executes inline so this task is a stub that
  refuses to run until the Phase 2 dispatcher arrives.

Both tasks honour AGENTS rule 4 (canonical progress frames via
:mod:`aqp.tasks._progress`) and rule 5 (cross-task state through
Postgres; no pickled ORM through Celery — we always pass IDs).
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.lab_tasks.run_lab_graph")
def run_lab_graph(
    self,
    graph_id: str,
    run_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Submit a persisted ``lab_graphs`` row through :class:`LabRuntime`.

    Errors are folded into a structured ``LabRunResult.to_dict()``;
    the route layer / WS consumer reads them off the ``lab_runs``
    row + the canonical progress frame.
    """
    task_id = self.request.id or run_id
    emit(task_id, "queued", f"lab.run_lab_graph queued for graph {graph_id}")

    # Inline imports per `.cursor/rules/tasks-api.mdc` (Celery tasks
    # don't transitively pull in FastAPI route modules at boot).
    try:
        from aqp.lab.runtime import runtime_for_graph_id
    except Exception as exc:  # noqa: BLE001 - never crash boot
        emit_error(task_id, f"lab runtime import failed: {exc}")
        raise

    try:
        runtime = runtime_for_graph_id(
            graph_id,
            run_id=run_id,
            task_id=task_id,
            session_id=session_id,
        )
    except KeyError as exc:
        emit_error(task_id, f"graph {graph_id!r} not found")
        return {"status": "error", "error": str(exc), "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        logger.exception("runtime_for_graph_id failed")
        emit_error(task_id, f"runtime construction failed: {exc}")
        return {"status": "error", "error": str(exc), "run_id": run_id}

    try:
        result = runtime.submit_run()
    except Exception as exc:  # noqa: BLE001
        logger.exception("lab runtime crashed")
        emit_error(task_id, f"lab runtime crashed: {exc}")
        return {"status": "error", "error": str(exc), "run_id": run_id}

    # ``submit_run`` already emits ``done`` / ``error`` envelopes on the
    # progress bus via the runtime's :func:`_finalise` path — the Celery
    # task body just needs to return the dict.
    payload = result.to_dict()
    if result.status not in {"done", "halted", "cancelled"}:
        # Ensure consumers see a terminal frame even when the runtime
        # short-circuited compliance checks without touching task_id.
        try:
            if result.status == "error":
                emit_error(task_id, result.error or "lab run errored")
            else:
                emit_done(task_id, payload)
        except Exception:  # noqa: BLE001
            logger.debug("terminal frame fallback failed", exc_info=True)
    return payload


@celery_app.task(bind=True, name="aqp.tasks.lab_tasks.run_lab_node")
def run_lab_node(
    self,
    graph_id: str,
    run_id: str,
    node_id: str,
    upstream_locators: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Per-node Celery wrapper used by the Testing canvas.

    Supports two callers:

    1. "Run only this node" affordance from the canvas — the frontend
       dispatches ``run_lab_node`` directly with the node id; we
       emit canonical ``node:start`` / ``node:done`` / ``node:error``
       frames so the pill switches in real time without re-running
       the whole graph.
    2. The Phase 3+ ``celery.canvas.chain`` distributor — upstream
       tasks pass their ``output_locator`` dicts via
       ``upstream_locators`` so the executor can resolve them
       through the standard
       :func:`aqp.lab.executors._helpers.resolve_upstream_frame`
       path.

    Both paths share the same audit / metric ledger entry written
    via :class:`LabNodeRun` so the run-history drawer shows them
    uniformly. Errors are folded into a structured payload (rule 4 +
    rule 5) and never raise back to the broker — Celery's retry
    semantics aren't appropriate for user code failures.
    """
    task_id = self.request.id or f"{run_id}:{node_id}"
    emit(task_id, "queued", f"lab.run_lab_node queued node={node_id}", run_id=run_id, node_id=node_id)

    try:
        from aqp.lab.executors._types import NodeContext
        from aqp.lab.registry import resolve_executor
        from aqp.lab.schema import GraphSpec
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabGraph, LabNodeRun
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"lab module imports failed: {exc}", run_id=run_id, node_id=node_id)
        return {"status": "error", "error": str(exc), "run_id": run_id, "node_id": node_id}

    try:
        with SessionLocal() as session:
            graph_row = session.get(LabGraph, graph_id)
            if graph_row is None:
                emit_error(task_id, f"graph {graph_id!r} not found", run_id=run_id, node_id=node_id)
                return {
                    "status": "error",
                    "error": f"graph {graph_id!r} not found",
                    "run_id": run_id,
                    "node_id": node_id,
                }
            spec = GraphSpec.model_validate(graph_row.spec)
    except Exception as exc:  # noqa: BLE001
        emit_error(task_id, f"graph load failed: {exc}", run_id=run_id, node_id=node_id)
        return {"status": "error", "error": str(exc), "run_id": run_id, "node_id": node_id}

    node = next((n for n in spec.nodes if n.id == node_id), None)
    if node is None:
        emit_error(task_id, f"node {node_id!r} not in graph {graph_id!r}", run_id=run_id)
        return {
            "status": "error",
            "error": f"node {node_id!r} not in graph",
            "run_id": run_id,
            "node_id": node_id,
        }

    ctx = NodeContext(
        run_id=run_id,
        node_id=node_id,
        node_type=node.type,
        upstream=dict(upstream_locators or {}),
        task_id=task_id,
        request_context=None,
        extras={},
    )

    import time

    started = time.perf_counter()
    emit(
        task_id,
        "node:start",
        f"node {node_id} ({node.type}) started",
        run_id=run_id,
        node_id=node_id,
        node_type=node.type,
    )
    try:
        executor = resolve_executor(node.type)
        result = executor(node, ctx)
    except Exception as exc:  # noqa: BLE001
        duration_ms = (time.perf_counter() - started) * 1000.0
        logger.exception("lab.run_lab_node executor crashed")
        emit_error(
            task_id,
            f"executor crashed: {exc}",
            run_id=run_id,
            node_id=node_id,
            duration_ms=round(duration_ms, 3),
        )
        _record_lab_node_run(
            run_id=run_id,
            node_id=node_id,
            node_type=node.type,
            status="error",
            error=str(exc),
            duration_ms=duration_ms,
        )
        return {
            "status": "error",
            "error": str(exc),
            "run_id": run_id,
            "node_id": node_id,
        }

    duration_ms = (time.perf_counter() - started) * 1000.0
    stage = "node:done" if result.status == "done" else f"node:{result.status}"
    emit(
        task_id,
        stage,
        f"node {node_id} {result.status}",
        run_id=run_id,
        node_id=node_id,
        node_type=node.type,
        duration_ms=round(duration_ms, 3),
        metrics=result.metrics,
    )
    _record_lab_node_run(
        run_id=run_id,
        node_id=node_id,
        node_type=node.type,
        status=result.status,
        error=result.error,
        duration_ms=duration_ms,
        output_locator=result.output_locator,
        metrics=result.metrics,
    )
    return {
        "status": result.status,
        "error": result.error,
        "run_id": run_id,
        "node_id": node_id,
        "duration_ms": round(duration_ms, 3),
        "output_locator": dict(result.output_locator or {}),
        "metrics": dict(result.metrics or {}),
    }


def _record_lab_node_run(
    *,
    run_id: str,
    node_id: str,
    node_type: str,
    status: str,
    error: str | None,
    duration_ms: float,
    output_locator: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Persist a ``LabNodeRun`` row matching the inline-canvas writer.

    Mirrors :meth:`LabRuntime._record_node_run_row` so per-node
    Celery dispatch produces the same ledger shape as inline runs.
    Failures are swallowed — never block the task on persistence.
    """
    try:
        from datetime import datetime

        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_lab import LabNodeRun

        now = datetime.utcnow()
        with SessionLocal() as session:
            row = LabNodeRun(
                run_id=run_id,
                node_id=node_id,
                node_type=node_type,
                status=status,
                output_locator=dict(output_locator or {}),
                metrics=dict(metrics or {}),
                error=error,
                duration_ms=float(duration_ms),
                started_at=now,
                ended_at=now,
            )
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001
        logger.debug("record_lab_node_run failed", exc_info=True)


__all__ = ["run_lab_graph", "run_lab_node"]
