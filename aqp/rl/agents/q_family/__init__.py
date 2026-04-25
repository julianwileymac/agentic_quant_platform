"""Q-learning family agents (Huseinzol05 /agent, AFML ch. 14).

All variants share :class:`BaseQAgent` — a small PyTorch DQN with plug-in
network topologies. Concrete classes differ in:

* **Vanilla** — single Q-network.
* **Double** — target network for next-action Q lookup.
* **Duel** — separate value + advantage streams.
* **Recurrent** — LSTM encoder over an observation window.
* **Curiosity** — adds an intrinsic-reward head (ICM-style forward model).
"""
from __future__ import annotations

from aqp.rl.agents.q_family.base import BaseQAgent
from aqp.rl.agents.q_family.curiosity_q import CuriosityQAgent
from aqp.rl.agents.q_family.double_q import DoubleQAgent
from aqp.rl.agents.q_family.duel_q import DuelQAgent
from aqp.rl.agents.q_family.q_learning import QLearningAgent
from aqp.rl.agents.q_family.recurrent_q import RecurrentQAgent

__all__ = [
    "BaseQAgent",
    "CuriosityQAgent",
    "DoubleQAgent",
    "DuelQAgent",
    "QLearningAgent",
    "RecurrentQAgent",
]
