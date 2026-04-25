"""LLM-driven stock screening / selection agents.

Implements :class:`aqp.core.interfaces.IUniverseSelectionModel` so the
screener plugs straight into the 5-stage strategy framework.
"""
from __future__ import annotations

from aqp.agents.screening.llm_screener import LLMScreener, LLMScreenerAlpha

__all__ = ["LLMScreener", "LLMScreenerAlpha"]
