"""Trader-team agents: LLM-based signal emission with windowed RAG context.

Coexists with the existing :mod:`aqp.agents.trading` (CrewAI-style debate
trader). The new ``signal_emitter`` is the spec-driven entry point that
plugs into :class:`AgentRuntime` and the LangGraph orchestration.
"""
from __future__ import annotations

from aqp.agents.trader.signal_emitter import build_signal_emitter_spec

__all__ = ["build_signal_emitter_spec"]
