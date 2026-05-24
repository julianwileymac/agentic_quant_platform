"""Testing-mode compiler: GraphSpec → Celery canvas description.

Phase 0 ships the inline-execution plan; Phase 2 keeps the same plan
shape and adds a ``canvas_signature`` field describing the
``celery.canvas.chain`` the runtime can dispatch when
:attr:`settings.aqp_lab_inline_runs` is False. The runtime falls back
to the inline path when Celery isn't available so the dev loop keeps
working without a live worker.

Outputs pass via the ``output_locator`` JSON column on
``lab_node_runs`` (typically a MinIO Parquet URI or an in-process
Arrow blob — see :mod:`aqp.lab.executors`). Inter-task state never
gets pickled through Celery — AGENTS rule 5.
"""
from __future__ import annotations

from typing import Any

from aqp.lab.compiler import CompileContext, CompileResult
from aqp.lab.registry import get_node_type, known_aliases
from aqp.lab.schema import GraphSpec


def compile_testing(spec: GraphSpec, ctx: CompileContext) -> CompileResult:
    if spec.mode != "testing":
        raise ValueError(
            f"compile_testing requires mode='testing', got {spec.mode!r}"
        )

    aliases = set(known_aliases())
    order = spec.topological_order()
    plan: list[dict[str, Any]] = []
    upstream_map: dict[tuple[str, str], tuple[str, str]] = {}
    for edge in spec.edges:
        upstream_map[(edge.target, edge.target_port)] = (edge.source, edge.source_port)

    canvas_steps: list[dict[str, Any]] = []
    for node in order:
        wiring: dict[str, tuple[str, str]] = {}
        for port in node.inputs:
            key = (node.id, port.name)
            if key in upstream_map:
                wiring[port.name] = upstream_map[key]
        # Resolve the executor target so the Celery wrapper can dispatch
        # to ``run_lab_node`` with everything it needs.
        executor_path: str | None = None
        if node.type in aliases:
            try:
                executor_path = get_node_type(node.type).executor
            except KeyError:
                executor_path = None
        plan.append(
            {
                "node_id": node.id,
                "node_type": node.type,
                "category": node.category,
                "params": dict(node.params or {}),
                "wiring": wiring,
                "runtime": node.runtime.model_dump(mode="json"),
                "snapshot_inputs": node.snapshot_inputs,
                "executor": executor_path,
            }
        )
        # ``canvas_signature`` is a serialisable description the runtime
        # can pass into ``run_lab_node.s(...)`` when it wants to switch
        # to real Celery dispatch. Today we keep it as a list of
        # task-signature dicts so the wrapper can hand them to
        # ``celery.chain`` / ``chord`` without re-deriving them.
        canvas_steps.append(
            {
                "task_name": "aqp.tasks.lab_tasks.run_lab_node",
                "queue": node.runtime.queue or "lab.cpu",
                "kwargs": {
                    "run_id": ctx.run_id,
                    "node_id": node.id,
                },
            }
        )

    return CompileResult(
        mode="testing",
        target="celery_canvas",
        payload={
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "session_id": ctx.session_id,
            "lab_id": ctx.lab_id,
            "plan": plan,
            "canvas_signature": canvas_steps,
        },
        breadcrumbs=[
            {
                "compiler": "testing",
                "n_nodes": len(plan),
                "n_edges": len(spec.edges),
                "n_canvas_steps": len(canvas_steps),
            }
        ],
    )


__all__ = ["compile_testing"]
