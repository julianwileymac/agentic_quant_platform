"""Research-team agents (news mining, equity research, universe selection).

Specs are also expressible via :file:`configs/agents/*.yaml` and loaded
by :mod:`aqp.agents.registry`. The hand-written builders here exist so
callers can build the spec in code (handy for tests / one-off runs)
without touching the YAML.
"""
from __future__ import annotations

from aqp.agents.research.equity_researcher import build_equity_researcher_spec
from aqp.agents.research.news_miner import build_news_miner_spec
from aqp.agents.research.universe_selector import build_universe_selector_spec

__all__ = [
    "build_equity_researcher_spec",
    "build_news_miner_spec",
    "build_universe_selector_spec",
]
