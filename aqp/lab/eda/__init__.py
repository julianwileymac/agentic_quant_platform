"""EDA mode — long-lived reactive cell DAG per session.

Reuses :class:`aqp.dagster.sandbox.runtime.SandboxRuntime`-style
isolation (per-session tempdir + Redis namespace via
:class:`SandboxRedisNamespace`) so each operator's EDA workspace is
isolated from every other. The kernel preloads pandas / numpy / duckdb
/ polars / matplotlib (and vectorbt-pro when its licence is present),
and exposes the canonical AQP read helpers under safe stubs.

Cells form a directed acyclic graph driven by static AST analysis
(mirrors marimo): each cell's references / definitions are extracted
without executing it, edges are inserted upstream → downstream, and
edits mark every downstream cell stale. The kernel emits typed
:class:`EdaCellResultEnvelope` frames through the canonical
:func:`aqp.tasks._progress.emit` bus so the WS fanout in
:mod:`aqp.lab.ws.fanout` picks them up unchanged.
"""
from __future__ import annotations

from aqp.lab.eda.cell_dag import (
    CellDependencies,
    CellGraph,
    CellNode,
    analyse_cell_dependencies,
)
from aqp.lab.eda.kernel import EdaKernel, EdaKernelRegistry, default_kernel_registry

__all__ = [
    "CellDependencies",
    "CellGraph",
    "CellNode",
    "EdaKernel",
    "EdaKernelRegistry",
    "analyse_cell_dependencies",
    "default_kernel_registry",
]
