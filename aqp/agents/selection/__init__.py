"""Selection-team agents: pick the best stocks for a (model, strategy, universe, agent) combo."""
from __future__ import annotations

from aqp.agents.selection.annotation_writer import write_selection_annotation
from aqp.agents.selection.stock_selector import build_stock_selector_spec

__all__ = ["build_stock_selector_spec", "write_selection_annotation"]
