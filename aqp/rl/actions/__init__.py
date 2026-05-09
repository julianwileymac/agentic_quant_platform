"""Action-space library — re-exports the concrete classes from
:mod:`aqp.rl.core.action`.

The core module ships the canonical implementations
(``ContinuousWeightsAction``, ``SoftmaxWeightsAction``,
``IntegerSharesAction``, ``DiscreteBuySellHoldAction``,
``MultiDiscreteAction``, ``TargetPositionAction``); this package exists
so users can import from a stable :mod:`aqp.rl.actions` namespace just
like :mod:`aqp.rl.rewards` and :mod:`aqp.rl.observations`.
"""
from __future__ import annotations

from aqp.rl.core.action import (
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
