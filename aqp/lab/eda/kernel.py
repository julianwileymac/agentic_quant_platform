"""Long-lived per-session EDA kernel.

Each :class:`EdaKernel` owns:

- A per-session Python namespace that survives across cell executions
  (the reactive REPL).
- A :class:`CellGraph` rebuilt whenever a cell is added / edited.
- A bounded ring of the last-N cell outcomes for the run-history drawer.

For Phase 1 the kernel runs in-process (one kernel per Python worker).
The :class:`EdaKernelRegistry` indexes kernels by ``session_id`` so the
WS route can dispatch ``eda.exec`` envelopes into the same namespace
across a session.

Sandboxing posture:

- The kernel REJECTS any cell that fails the
  :func:`aqp.data.expressions_dsl`-style AST guard (no
  :func:`os.system`, no :func:`subprocess`, no :func:`eval` /
  :func:`exec` of dynamically-constructed strings, no
  ``__import__("ctypes")``) — see :func:`_aast_safety_check`. Phase 5
  swaps the in-process path for a gVisor-Docker sandbox per AGENTS
  rule 45.
- Stdout / stderr from cell execution is captured + truncated; no
  cell can spam Redis directly.
- We share the kernel's Python interpreter for now — multi-tenant
  isolation is process-level (one Celery worker per tenant) in Phase
  1, container-level in Phase 5.
"""
from __future__ import annotations

import ast
import builtins
import io
import logging
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Iterable

from aqp.lab.eda.cell_dag import (
    CellGraph,
    CellNode,
    build_cell_graph,
    stale_descendants_of,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AST safety guard (always-on)
# ---------------------------------------------------------------------------


_FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "__import__", "open"})
_FORBIDDEN_ATTRS = frozenset({"system", "popen", "spawn", "Popen", "call", "run"})


class CellSafetyError(ValueError):
    """Raised when a cell fails the AST safety guard."""


def _ast_safety_check(source: str) -> None:
    """Reject obviously dangerous constructs BEFORE exec.

    Mirrors the spirit of :mod:`aqp.data.expressions_dsl` — the check
    is not a security boundary (it can be evaded), it's a friendly
    pre-flight that catches accidents and ships fast feedback to the
    cell editor.
    """
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return  # the executor surfaces the syntax error naturally

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _FORBIDDEN_CALLS:
                raise CellSafetyError(
                    f"cell uses forbidden builtin {fn.id!r}; "
                    "use the kernel's bundled helpers (db.scan / iceberg) instead"
                )
            if isinstance(fn, ast.Attribute):
                if (
                    isinstance(fn.value, ast.Name)
                    and fn.value.id in {"os", "subprocess", "ctypes"}
                ):
                    raise CellSafetyError(
                        f"cell uses forbidden module call {fn.value.id}.{fn.attr}"
                    )
                if fn.attr in _FORBIDDEN_ATTRS and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                    raise CellSafetyError(
                        f"cell uses forbidden os.{fn.attr} call"
                    )
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"ctypes", "subprocess"}:
                    raise CellSafetyError(
                        f"cell imports forbidden module {alias.name!r}"
                    )
        if isinstance(node, ast.ImportFrom):
            if (node.module or "") in {"ctypes", "subprocess"}:
                raise CellSafetyError(
                    f"cell imports forbidden module {node.module!r}"
                )


# ---------------------------------------------------------------------------
# Cell exec result
# ---------------------------------------------------------------------------


@dataclass
class CellExecResult:
    cell_id: str
    status: str  # done | error
    started_at: float
    duration_ms: float
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    repr_value: str | None = None
    render: dict[str, Any] = field(default_factory=dict)
    stale_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Kernel
# ---------------------------------------------------------------------------


class EdaKernel:
    """One long-lived reactive REPL per session."""

    def __init__(
        self,
        session_id: str,
        *,
        max_stdout_chars: int = 8_000,
        max_repr_chars: int = 2_000,
    ) -> None:
        self.session_id = session_id
        self._lock = threading.RLock()
        self._namespace: dict[str, Any] = self._build_preloaded_namespace()
        self._cells: dict[str, CellNode] = {}
        self._next_ord = 0
        self._max_stdout_chars = max_stdout_chars
        self._max_repr_chars = max_repr_chars
        self._created_at = time.time()
        self._last_active = time.time()

    # ------------------------------------------------------------------ public

    def upsert_cell(self, cell_id: str, source: str, *, ord: int | None = None) -> CellNode:
        """Add or replace a cell. Marks descendants stale."""
        with self._lock:
            existing = self._cells.get(cell_id)
            if existing is None:
                ord_value = ord if ord is not None else self._next_ord
                self._next_ord = max(self._next_ord + 1, ord_value + 1)
                node = CellNode(id=cell_id, source=source or "", ord=ord_value)
                self._cells[cell_id] = node
            else:
                existing.source = source or ""
                if ord is not None:
                    existing.ord = ord
                existing.stale = True
                node = existing
            graph = self._rebuild_graph()
            stale = stale_descendants_of(graph, cell_id)
            for sid in stale:
                if sid in self._cells:
                    self._cells[sid].stale = True
            self._last_active = time.time()
            return node

    def remove_cell(self, cell_id: str) -> list[str]:
        """Drop a cell. Returns the descendants that become stale."""
        with self._lock:
            cell = self._cells.pop(cell_id, None)
            if cell is None:
                return []
            graph = self._rebuild_graph()
            stale_ids = list(stale_descendants_of(graph, cell_id))
            for sid in stale_ids:
                if sid in self._cells:
                    self._cells[sid].stale = True
            return stale_ids

    def graph_snapshot(self) -> CellGraph:
        with self._lock:
            return self._rebuild_graph()

    def stale_descendants(self, cell_id: str) -> list[str]:
        with self._lock:
            return stale_descendants_of(self._rebuild_graph(), cell_id)

    def execute_cell(self, cell_id: str, source: str | None = None) -> CellExecResult:
        """Run a single cell, capturing stdout / stderr / repr."""
        with self._lock:
            self.upsert_cell(cell_id, source if source is not None else self._cells.get(cell_id, CellNode(id=cell_id, source="", ord=0)).source)
            cell = self._cells[cell_id]
            started = time.time()
            try:
                _ast_safety_check(cell.source)
            except CellSafetyError as exc:
                cell.last_error = str(exc)
                duration_ms = (time.time() - started) * 1000.0
                return CellExecResult(
                    cell_id=cell_id,
                    status="error",
                    started_at=started,
                    duration_ms=duration_ms,
                    error=str(exc),
                    render={"kind": "safety_error"},
                )

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            error: str | None = None
            repr_value: str | None = None
            try:
                # Compile then exec/eval. For a single-expression cell
                # we eval the expression so the repr surfaces back to
                # the UI; otherwise we exec the statement list.
                tree = ast.parse(cell.source or "", filename=f"<eda:{cell_id}>", mode="exec")
                last_expr = (
                    tree.body[-1]
                    if tree.body and isinstance(tree.body[-1], ast.Expr)
                    else None
                )
                exec_body = (
                    ast.Module(body=tree.body[:-1], type_ignores=[])
                    if last_expr
                    else tree
                )
                with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                    if exec_body.body:
                        exec(  # noqa: S102 — sandboxed via _ast_safety_check
                            compile(exec_body, f"<eda:{cell_id}>", "exec"),
                            self._namespace,
                            self._namespace,
                        )
                    if last_expr is not None:
                        value = eval(  # noqa: S307
                            compile(
                                ast.Expression(body=last_expr.value),
                                f"<eda:{cell_id}>",
                                "eval",
                            ),
                            self._namespace,
                            self._namespace,
                        )
                        if value is not None:
                            try:
                                repr_value = repr(value)
                            except Exception:  # noqa: BLE001
                                repr_value = "<unrepresentable>"
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                stderr_buf.write(traceback.format_exc(limit=6))

            duration_ms = (time.time() - started) * 1000.0
            cell.last_executed_at = time.time()
            cell.stale = False
            cell.last_error = error
            self._last_active = time.time()
            stale_ids = self.stale_descendants(cell_id)
            return CellExecResult(
                cell_id=cell_id,
                status="error" if error else "done",
                started_at=started,
                duration_ms=duration_ms,
                stdout=stdout_buf.getvalue()[: self._max_stdout_chars],
                stderr=stderr_buf.getvalue()[: self._max_stdout_chars],
                error=error,
                repr_value=(repr_value or "")[: self._max_repr_chars] or None,
                render={"kind": "repr", "value": repr_value} if repr_value else {},
                stale_ids=stale_ids,
            )

    def get_var(self, name: str) -> Any:
        with self._lock:
            return self._namespace.get(name)

    @property
    def created_at(self) -> float:
        return self._created_at

    @property
    def last_active(self) -> float:
        return self._last_active

    @property
    def cell_count(self) -> int:
        return len(self._cells)

    # ------------------------------------------------------------------ internals

    def _rebuild_graph(self) -> CellGraph:
        return build_cell_graph(self._cells.values())

    def _build_preloaded_namespace(self) -> dict[str, Any]:
        """Return the per-session globals dict.

        We preload safe stubs for the most common reads. Heavy
        dependencies (vectorbt-pro, polars, plotly) are imported
        lazily so kernel cold-start stays under the 8s p95 budget.
        """
        ns: dict[str, Any] = {"__builtins__": builtins}
        try:
            import pandas as pd

            ns["pd"] = pd
        except Exception:  # noqa: BLE001
            pass
        try:
            import numpy as np

            ns["np"] = np
        except Exception:  # noqa: BLE001
            pass
        try:
            import duckdb

            ns["duckdb"] = duckdb
            ns["db"] = duckdb.connect()
        except Exception:  # noqa: BLE001
            pass
        # The Iceberg read helper is wrapped in a closure to honour
        # AGENTS rule 3 (read side via iceberg_catalog.read_arrow):
        try:
            from aqp.data import iceberg_catalog

            def _scan(identifier: str, *, columns: list[str] | None = None, limit: int | None = None) -> Any:
                arrow_table = iceberg_catalog.read_arrow(
                    identifier, columns=columns, limit=limit
                )
                return arrow_table.to_pandas() if arrow_table is not None else None

            ns["iceberg"] = iceberg_catalog
            ns["scan"] = _scan
        except Exception:  # noqa: BLE001 - keep kernel importable without Iceberg
            pass
        return ns


# ---------------------------------------------------------------------------
# Registry (one kernel per session_id)
# ---------------------------------------------------------------------------


class EdaKernelRegistry:
    """Process-local registry of session_id → :class:`EdaKernel`."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._kernels: dict[str, EdaKernel] = {}

    def get_or_create(self, session_id: str) -> EdaKernel:
        with self._lock:
            kernel = self._kernels.get(session_id)
            if kernel is None:
                kernel = EdaKernel(session_id)
                self._kernels[session_id] = kernel
            return kernel

    def get(self, session_id: str) -> EdaKernel | None:
        with self._lock:
            return self._kernels.get(session_id)

    def remove(self, session_id: str) -> bool:
        with self._lock:
            return self._kernels.pop(session_id, None) is not None

    def session_ids(self) -> Iterable[str]:
        with self._lock:
            return list(self._kernels.keys())

    def expire_idle(self, *, ttl_seconds: float = 3600.0) -> int:
        now = time.time()
        expired: list[str] = []
        with self._lock:
            for sid, kernel in list(self._kernels.items()):
                if now - kernel.last_active > ttl_seconds:
                    expired.append(sid)
            for sid in expired:
                self._kernels.pop(sid, None)
        return len(expired)


_DEFAULT_REGISTRY = EdaKernelRegistry()


def default_kernel_registry() -> EdaKernelRegistry:
    return _DEFAULT_REGISTRY


__all__ = [
    "CellExecResult",
    "CellSafetyError",
    "EdaKernel",
    "EdaKernelRegistry",
    "default_kernel_registry",
]
