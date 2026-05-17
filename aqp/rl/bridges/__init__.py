"""Engine bridges — generalised ``context['rl_agent']`` channel.

This package houses the bridge primitives that let any registered
:class:`~aqp.backtest.base.BaseBacktestEngine` accept per-bar action
injection from a trained RL policy.

Architecture
------------

The :class:`RLAgentBridge` is the single object exposed to strategy
``on_bar`` / ``on_data`` calls as ``context['rl_agent']``. Strategies
call :meth:`RLAgentBridge.consult` exactly like they call the
existing ``context['agents']`` agent dispatcher; the returned object
is a :class:`RLDecision` carrying the target-weight vector + raw
action + the four-stage :class:`PipelineState` for audit.

This generalises the event-driven-only pattern in
:mod:`aqp.backtest.engine` (``_get_agent_dispatcher`` /
``context['agents']``) to every engine that flips
``EngineCapabilities.supports_rl_injection=True``.

Determinism: the bridge is single-threaded by construction. A
trained policy's ``predict`` call is a pure function of its input
state; deterministic mode (the default) further removes any
sampling noise so the bridge produces identical decisions across
replays.
"""
from __future__ import annotations

from aqp.rl.bridges.agent_bridge import (
    NoopRLAgentBridge,
    RLAgentBridge,
    RLDecision,
)

__all__ = [
    "NoopRLAgentBridge",
    "RLAgentBridge",
    "RLDecision",
]
