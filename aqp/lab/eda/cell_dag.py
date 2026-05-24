"""Marimo-style reactive cell DAG.

Each EDA cell is a small Python snippet. We statically analyse each
cell with :mod:`ast` to extract:

- ``defines`` — names this cell binds (assignments, function/class
  defs, for-loop targets, with-statement aliases).
- ``references`` — names this cell reads as :class:`ast.Load`
  contexts that are NOT defined locally and NOT in the kernel's
  builtin set.

Then for each cell we compute its upstream set as every other cell
whose ``defines`` intersect the current cell's ``references``. Edges
are inserted from upstream → downstream so editing a cell can
mark every transitive downstream cell stale.

Pure static analysis — we never execute user code in this module.
Anything the AST cannot resolve falls back to "treat as a reference"
so the user gets a stale-pill rather than a silent miss.
"""
from __future__ import annotations

import ast
import builtins
import logging
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


# Builtin names that don't count as cross-cell references.
_BUILTINS = frozenset(dir(builtins))
# Common preloaded import aliases that don't count as cross-cell
# references (the kernel exposes these globally so any cell can use
# them without re-importing).
_PRELOADED = frozenset(
    {
        "pd",
        "np",
        "duckdb",
        "polars",
        "pl",
        "plt",
        "vbt",
        "db",
        "iceberg",
        "scan",
        "load",
        "session",
    }
)


@dataclass(frozen=True)
class CellDependencies:
    """References + definitions extracted from one cell's AST."""

    cell_id: str
    defines: frozenset[str]
    references: frozenset[str]
    imports: frozenset[str]
    syntax_ok: bool
    error: str | None = None


@dataclass
class CellNode:
    """One cell in the reactive DAG."""

    id: str
    source: str
    ord: int
    deps: CellDependencies | None = None
    upstream: set[str] = field(default_factory=set)
    downstream: set[str] = field(default_factory=set)
    stale: bool = False
    last_executed_at: float | None = None
    last_error: str | None = None


@dataclass
class CellGraph:
    """Ordered cell list + the derived dependency graph."""

    cells: list[CellNode] = field(default_factory=list)

    def index(self) -> dict[str, CellNode]:
        return {c.id: c for c in self.cells}

    def order_by_seq(self) -> list[CellNode]:
        return sorted(self.cells, key=lambda c: c.ord)


# ---------------------------------------------------------------------------
# AST visitor
# ---------------------------------------------------------------------------


class _ScopeWalker(ast.NodeVisitor):
    """Walk a cell-level AST and collect ``defines`` + ``references``.

    We deliberately treat each cell as ONE scope — function bodies are
    NOT recursed into for the cross-cell dependency analysis because
    marimo semantics only care about top-level globals. (We DO recurse
    into class bodies because class-level statements that read a name
    still form a cross-cell dependency.)
    """

    def __init__(self) -> None:
        self.defines: set[str] = set()
        self.references: set[str] = set()
        self.imports: set[str] = set()

    # -- assignment / definition forms

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_targets(target)
        self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._record_targets(node.target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._record_targets(node.target)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.annotation)

    def visit_For(self, node: ast.For) -> None:
        self._record_targets(node.target)
        self.visit(node.iter)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                self._record_targets(item.optional_vars)
        for stmt in node.body:
            self.visit(stmt)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defines.add(node.name)
        # Do NOT recurse into function bodies for cross-cell deps —
        # marimo's analyser does the same to avoid spurious edges.

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.defines.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defines.add(node.name)
        # Class-level statements DO count for cross-cell deps because
        # they execute at class definition time.
        for stmt in node.body:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.imports.add(alias.asname or alias.name)

    # -- reference forms

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.references.add(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.defines.add(node.id)

    # -- comprehensions create a nested scope for the iteration
    # variables; we still track the outer references.

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comp(node, node.generators)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comp(node, node.generators)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comp(node, node.generators)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comp(node, node.generators)

    def _visit_comp(self, node: ast.AST, generators: list[ast.comprehension]) -> None:
        # Comprehension targets are scope-local; we drop them from the
        # cell-level ``defines``. Iter / element exprs still count for
        # references.
        comp_targets: set[str] = set()
        prev_defines = set(self.defines)
        for gen in generators:
            self._collect_target_names(gen.target, into=comp_targets)
            self.visit(gen.iter)
            for if_ in gen.ifs:
                self.visit(if_)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.comprehension):
                continue
            self.visit(child)
        self.defines = prev_defines  # discard comprehension-local binds
        self.references.difference_update(comp_targets)

    # -- helpers

    def _record_targets(self, target: ast.AST) -> None:
        self._collect_target_names(target, into=self.defines)

    def _collect_target_names(self, target: ast.AST, *, into: set[str]) -> None:
        if isinstance(target, ast.Name):
            into.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._collect_target_names(elt, into=into)
        elif isinstance(target, ast.Starred):
            self._collect_target_names(target.value, into=into)
        elif isinstance(target, (ast.Attribute, ast.Subscript)):
            # Mutating a.b or a[i] doesn't bind a new top-level name;
            # treat as a reference to the base name instead.
            base = target
            while isinstance(base, (ast.Attribute, ast.Subscript)):
                base = base.value
            if isinstance(base, ast.Name):
                self.references.add(base.id)


def analyse_cell_dependencies(cell_id: str, source: str) -> CellDependencies:
    """Static analysis of one cell. Never raises."""
    try:
        tree = ast.parse(source or "", filename=f"<eda:{cell_id}>")
    except SyntaxError as exc:
        return CellDependencies(
            cell_id=cell_id,
            defines=frozenset(),
            references=frozenset(),
            imports=frozenset(),
            syntax_ok=False,
            error=str(exc),
        )
    walker = _ScopeWalker()
    for stmt in tree.body:
        walker.visit(stmt)
    # Discard imports + builtins + preloaded helpers from references.
    refs = walker.references - walker.imports - walker.defines - _BUILTINS - _PRELOADED
    return CellDependencies(
        cell_id=cell_id,
        defines=frozenset(walker.defines),
        references=frozenset(refs),
        imports=frozenset(walker.imports),
        syntax_ok=True,
    )


# ---------------------------------------------------------------------------
# Graph building
# ---------------------------------------------------------------------------


def build_cell_graph(cells: Iterable[CellNode]) -> CellGraph:
    """Compute upstream / downstream sets for every cell in order."""
    ordered = sorted(list(cells), key=lambda c: c.ord)
    by_id = {c.id: c for c in ordered}
    for c in ordered:
        c.deps = analyse_cell_dependencies(c.id, c.source)
        c.upstream = set()
        c.downstream = set()

    for i, c in enumerate(ordered):
        if c.deps is None:
            continue
        for ref in c.deps.references:
            # Walk earlier cells (smaller ord) and link the most-recent
            # definer of this ref. Multiple definers earlier in the
            # ordering are all valid upstreams; we take the LAST one
            # that defined the name so the graph reflects shadowing
            # semantics correctly.
            for j in range(i - 1, -1, -1):
                prev = ordered[j]
                if prev.deps and ref in prev.deps.defines:
                    c.upstream.add(prev.id)
                    prev.downstream.add(c.id)
                    break

    # Recompute downstream from the upstream edges so downstream sets
    # are always complete (the visit above only adds direct edges).
    descendants: dict[str, set[str]] = {c.id: set() for c in ordered}
    for c in ordered:
        for up in c.upstream:
            descendants.setdefault(up, set()).add(c.id)
    for c in ordered:
        # Transitive closure.
        seen: set[str] = set()
        frontier = list(descendants.get(c.id, set()))
        while frontier:
            nxt = frontier.pop()
            if nxt in seen:
                continue
            seen.add(nxt)
            frontier.extend(descendants.get(nxt, set()))
        c.downstream = seen
        if c.id in by_id:
            by_id[c.id] = c

    return CellGraph(cells=ordered)


def stale_descendants_of(graph: CellGraph, edited_cell_id: str) -> list[str]:
    """Return the deterministic list of downstream cells to mark stale."""
    target = next((c for c in graph.cells if c.id == edited_cell_id), None)
    if target is None:
        return []
    return sorted(target.downstream)


__all__ = [
    "CellDependencies",
    "CellGraph",
    "CellNode",
    "analyse_cell_dependencies",
    "build_cell_graph",
    "stale_descendants_of",
]
