"""Action-space library — re-exports the concrete classes from
:mod:`aqp_rl.core.action`.

The core module ships the canonical implementations
(``ContinuousWeightsAction``, ``SoftmaxWeightsAction``,
``IntegerSharesAction``, ``DiscreteBuySellHoldAction``,
``MultiDiscreteAction``, ``TargetPositionAction``); this package exists
so users can import from a stable :mod:`aqp_rl.actions` namespace just
like :mod:`aqp_rl.rewards` and :mod:`aqp_rl.observations`.
"""
from __future__ import annotations

from aqp_rl.core.action import (
    BaseActionSpace,
    ContinuousWeightsAction,
    DiscreteBuySellHoldAction,
    IntegerSharesAction,
    MultiDiscreteAction,
    SoftmaxWeightsAction,
    TargetPositionAction,
)

__all__ = [
    "BaseActionSpace",
    "ContinuousWeightsAction",
    "DiscreteBuySellHoldAction",
    "IntegerSharesAction",
    "MultiDiscreteAction",
    "SoftmaxWeightsAction",
    "TargetPositionAction",
]
