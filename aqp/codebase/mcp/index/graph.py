"""Adjacency-graph view of a codebase symbol set.

The graph captures three relationships:

- ``file -> symbol`` — every parsed file ``contains`` its top-level
  classes / functions / constants / imports.
- ``class -> method`` — class symbols ``define`` their nested
  methods (via ``Symbol.parent``).
- ``file -> file`` — Python imports contribute ``imports`` edges so
  agents can ask "which files depend on ``aqp.kubernetes.protocol``?".

The implementation uses a dict-of-sets adjacency map (no networkx
dependency) so the codebase MCP installs cleanly on the slimmest AQP
profile. Adding ``networkx`` later is straightforward — only the
``CodeGraph.as_dict`` exporter needs to change.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from aqp.codebase.mcp.index.ast_index import Symbol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GraphEdge:
    src: str
    dst: str
    kind: str  # "contains" | "defines" | "imports"


@dataclass(slots=True)
class CodeGraph:
    nodes: set[str] = field(default_factory=set)
    edges: list[GraphEdge] = field(default_factory=list)
    by_file: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))
    by_name: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))

    def add_node(self, node_id: str) -> None:
        self.nodes.add(node_id)

    def add_edge(self, src: str, dst: str, kind: str) -> None:
        self.add_node(src)
        self.add_node(dst)
        self.edges.append(GraphEdge(src=src, dst=dst, kind=kind))

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def neighbours(self, node: str, *, kind: str | None = None) -> list[str]:
        out: list[str] = []
        for edge in self.edges:
            if edge.src == node and (kind is None or edge.kind == kind):
                out.append(edge.dst)
        return out

    def reverse_neighbours(self, node: str, *, kind: str | None = None) -> list[str]:
        out: list[str] = []
        for edge in self.edges:
            if edge.dst == node and (kind is None or edge.kind == kind):
                out.append(edge.src)
        return out

    def slice(self, *, file: str | None = None, depth: int = 1) -> dict[str, list[str]]:
        """Return an adjacency slice rooted at ``file`` up to ``depth`` hops."""
        if file is None:
            return {node: self.neighbours(node) for node in sorted(self.nodes)}
        seen: set[str] = {file}
        frontier: set[str] = {file}
        for _ in range(max(0, depth)):
            new_frontier: set[str] = set()
            for n in frontier:
                for nb in self.neighbours(n):
                    if nb not in seen:
                        seen.add(nb)
                        new_frontier.add(nb)
            frontier = new_frontier
            if not frontier:
                break
        return {n: self.neighbours(n) for n in sorted(seen)}

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "nodes": sorted(self.nodes),  # type: ignore[return-value]
            "edges": [
                {"src": e.src, "dst": e.dst, "kind": e.kind} for e in self.edges
            ],
        }


def build_graph_from_symbols(symbols: Iterable[Symbol]) -> CodeGraph:
    """Build a :class:`CodeGraph` from a flat iterable of symbols."""
    g = CodeGraph()
    for sym in symbols:
        g.by_file[sym.file].append(sym)
        g.by_name[sym.name].append(sym)
        g.add_node(sym.file)
        if sym.kind == "module":
            continue
        # File `contains` symbol; class `defines` method.
        symbol_id = f"{sym.file}::{sym.parent}.{sym.name}" if sym.parent else f"{sym.file}::{sym.name}"
        g.add_node(symbol_id)
        g.add_edge(sym.file, symbol_id, "contains")
        if sym.parent:
            parent_id = f"{sym.file}::{sym.parent}"
            g.add_edge(parent_id, symbol_id, "defines")
        if sym.kind == "import":
            module = sym.metadata.get("module") or sym.metadata.get("imported", "")
            if module:
                g.add_edge(sym.file, module, "imports")
    return g


__all__ = [
    "CodeGraph",
    "GraphEdge",
    "build_graph_from_symbols",
]
