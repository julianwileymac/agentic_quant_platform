"""Live-broker execution bridge for RL paper / live trading.

Closes the FinRL-X deployment-consistent loop on the live edge: the
target-weight vector ``w_t`` emitted by the trained RL policy (via
the :class:`aqp_rl.bridges.RLAgentBridge`) is translated into
broker-routed orders that match the offline simulation byte-for-byte.

The single sanctioned entry point is :func:`apply_target_weights`,
which:

1. Gates on :func:`aqp.risk.kill_switch.is_engaged` (rule 4 progress
   + draconian halt) before any broker call.
2. Computes per-symbol position deltas from
   ``IDomainBrokerage.fetch_positions``.
3. Submits :class:`DomainOrder` instances through the canonical
   :class:`IDomainBrokerage.submit` protocol.

The translator NEVER hand-writes a venue-specific order shape — every
order is a :class:`DomainOrder` subclass (rule "DomainOrder is the
canonical wire shape") so backtest + paper + live execution paths
share identical semantics.
"""
from __future__ import annotations

from aqp_rl.execution.weight_to_orders import (
    WeightToOrders,
    WeightToOrdersResult,
    apply_target_weights,
)

__all__ = [
    "WeightToOrders",
    "WeightToOrdersResult",
    "apply_target_weights",
]
