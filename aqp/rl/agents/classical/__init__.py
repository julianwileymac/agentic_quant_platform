"""Classical rule-based agents (Stock-Prediction-Models ``/agent``).

These agents take a price series and emit buy/sell/hold actions by pure
rules — no gradient training, no replay buffer. They implement the
``BaseClassicalAgent`` protocol so they can be swapped into any RL env
via :class:`aqp.strategies.rl_policy.RLPolicyAlpha`.

Handy for: rapid iteration, sanity baselines, and forming part of an
ensemble that a trainable RL agent can study.
"""
from __future__ import annotations

from aqp.rl.agents.classical.abcd import ABCDStrategyAgent
from aqp.rl.agents.classical.base import BaseClassicalAgent
from aqp.rl.agents.classical.moving_average import MovingAverageAgent
from aqp.rl.agents.classical.signal_rolling import SignalRollingAgent
from aqp.rl.agents.classical.turtle import TurtleAgent

__all__ = [
    "ABCDStrategyAgent",
    "BaseClassicalAgent",
    "MovingAverageAgent",
    "SignalRollingAgent",
    "TurtleAgent",
]
