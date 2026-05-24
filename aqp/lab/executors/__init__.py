"""Data Lab node executors.

Each executor exposes a single :func:`execute` callable with the
contract::

    def execute(node: NodeSpec, ctx: NodeContext) -> NodeResult:
        ...

The :class:`NodeContext` is the per-node runtime envelope passed by
the compiler (run_id, upstream artifacts as dict[str, str] URIs,
output sink, task_id, RequestContext). Executors do NOT call
:func:`aqp.tasks._progress.emit` themselves; the surrounding Celery
task wrapper in :mod:`aqp.tasks.lab_tasks` is the canonical caller of
the progress bus per AGENTS rule 4.

Phase 0 ships three real executors plus a structured placeholder.
Phases 2-5 fill in the rest.
"""
from __future__ import annotations

from aqp.lab.executors._types import NodeContext, NodeResult

__all__ = ["NodeContext", "NodeResult"]
