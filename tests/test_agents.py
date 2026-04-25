"""Smoke tests for the agent tools and memory (does not call the LLM)."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_bm25_memory_roundtrip(tmp_path: Path) -> None:
    from aqp.llm.memory import BM25Memory

    mem = BM25Memory(role="tester", persist_dir=tmp_path)
    mem.add("high volatility regime, low breadth", "reduce gross exposure to 30%")
    mem.add("mean-reverting low-vol stocks", "use z-score threshold of 2")
    hits = mem.recall("low volatility", k=2)
    assert len(hits) >= 1
    assert any("z-score" in h.lesson for h in hits)


def test_tool_registry_names() -> None:
    pytest.importorskip("crewai")
    from aqp.agents.tools import get_tool

    for name in (
        "duckdb_query",
        "describe_bars",
        "chroma_search",
        "directory_read",
        "backtest",
        "walk_forward",
        "risk_check",
        "kill_switch",
        "ledger",
        "metrics",
        "plotly",
    ):
        assert get_tool(name) is not None


def test_crew_config_loads() -> None:
    import yaml

    cfg = yaml.safe_load(Path("configs/agents/research_crew.yaml").read_text(encoding="utf-8"))
    assert "agents" in cfg
    assert "tasks" in cfg
