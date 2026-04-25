"""Gradient-free evolutionary agents.

* :class:`EvolutionStrategyAgent` — OpenAI-style ES over a dense policy.
* :class:`NeuroEvolutionAgent` — population of MLPs evolved via crossover
  + mutation.
* :class:`NeuroEvolutionNoveltyAgent` — NES variant that scores fitness by
  behavioural novelty instead of raw reward.
"""
from __future__ import annotations

from aqp.rl.agents.evolutionary.es import EvolutionStrategyAgent
from aqp.rl.agents.evolutionary.novelty import NeuroEvolutionNoveltyAgent
from aqp.rl.agents.evolutionary.neuro import NeuroEvolutionAgent

__all__ = [
    "EvolutionStrategyAgent",
    "NeuroEvolutionAgent",
    "NeuroEvolutionNoveltyAgent",
]
