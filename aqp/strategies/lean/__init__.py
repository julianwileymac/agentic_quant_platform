"""LEAN strategy template helpers (Phase 7 of the multi-tenant rollout).

Two surfaces:

- :mod:`aqp.strategies.lean.translator` — AST-driven translator that
  takes the source of a QuantConnect LEAN ``QCAlgorithm`` subclass and
  emits an :class:`aqp.strategies.framework.FrameworkAlgorithm`
  skeleton. The skeleton handles the common patterns (Initialize ->
  prepare, OnData -> on_bar, AddEquity/AddOption -> universe spec,
  self.MACD/SMA/etc. -> aqp.data.indicators); anything unmapped
  becomes a ``# TODO(lean-translate)`` comment so users can finish
  the port manually.
- :mod:`aqp.strategies.lean.parser` — lightweight AST inspector that
  pulls the class name, base class, docstring, indicators referenced,
  asset class hints, and tag list. Powers the
  :file:`scripts/ingest_lean_templates.py` ingester.

The ingester runs once per LEAN release; the translator runs on demand
via the ``data.strategies.templates.clone_to_workspace`` MCP tool.
"""
from __future__ import annotations

from aqp.strategies.lean.parser import LeanTemplateInfo, parse_lean_source
from aqp.strategies.lean.translator import translate_lean_to_framework

__all__ = [
    "LeanTemplateInfo",
    "parse_lean_source",
    "translate_lean_to_framework",
]
