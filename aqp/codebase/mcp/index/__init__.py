"""Indexing primitives for the codebase MCP.

- :mod:`aqp.codebase.mcp.index.ast_index` — language-aware AST parsing
  via tree-sitter when available, with a Python-only ``ast`` fallback.
- :mod:`aqp.codebase.mcp.index.graph` — networkx graph of file →
  class → function → call relationships, cached on disk.
- :mod:`aqp.codebase.mcp.index.embeddings` — bridge from code chunks
  into the ``code_chunks`` RAG corpus via :class:`HierarchicalRAG`.
- :mod:`aqp.codebase.mcp.index.ripgrep` — thin wrapper around ``rg`` /
  pure-Python regex fallback.
"""
from __future__ import annotations

from aqp.codebase.mcp.index.ast_index import (
    Symbol,
    SymbolKind,
    index_file,
    index_workspace,
)
from aqp.codebase.mcp.index.graph import CodeGraph, build_graph_from_symbols
from aqp.codebase.mcp.index.ripgrep import LexicalMatch, ripgrep_search

__all__ = [
    "CodeGraph",
    "LexicalMatch",
    "Symbol",
    "SymbolKind",
    "build_graph_from_symbols",
    "index_file",
    "index_workspace",
    "ripgrep_search",
]
