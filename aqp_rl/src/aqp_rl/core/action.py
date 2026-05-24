"""Action space contract — declarative ``gym.spaces`` plus ``transform``.

Each action space subclass:

1. Declares the underlying Gym space via :meth:`gym_space()`
   (used by :class:`BaseRLEnv` to populate ``self.action_space``).
2. Implements :meth:`transform(raw_action)` which converts whatever the
   policy emitted into the canonical env action representation
   (clipped weights, integer share counts, target positions…).
3. Optionally implements :meth:`validate(action)` — raises ``ValueError``
   when the policy emits something out-of-range.

Concrete classes ship in :mod:`aqp_rl.actions.*` but the most common
trading representations are also pre-registered here so the RL Lab
palette has them available out-of-the-box without importing the
sub-package.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

import numpy as np
from gymnasium import spaces

from aqp_rl.core.base import RL_KIND_ACTION, RLComponent


class BaseActionSpace(RLComponent):
    """Abstract action space.

    Subclasses set ``n_assets`` (or accept it via constructor) so the
    declared :class:`gymnasium.Space` matches the env's universe size.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_ACTION

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def gym_space(self) -> spaces.Space:  # pragma: no cover - abstract
        """Return the :class:`gymnasium.Space` for this action representation."""

    @abstractmethod
    def transform(self, raw_action: Any) -> Any:  # pragma: no cover - abstract
        """Convert a raw policy output into the canonical env action."""

    def validate(self, action: Any) -> None:
        """Optional validation hook (raise ``ValueError`` on bad input)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "class": type(self).__name__,
            "name": self.name,
        }


# ---------------------------------------------------------------------------
# Concrete action spaces — pre-registered for the lab palette.
# ---------------------------------------------------------------------------


class ContinuousWeightsAction(BaseActionSpace):
    """Continuous weight vector in ``[low, high]^n_assets`` (with optional norm).

    Default behaviour matches the existing :class:`StockTradingEnv`:
    clip to ``[low, high]`` and renormalise so ``|sum(weights)| <= 1``.
    Used by PPO / A2C / SAC / DDPG / TD3 portfolios.
    """

    rl_alias: ClassVar[str] = "ContinuousWeightsAction"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "continuous"

    def __init__(
        self,
        n_assets: int,
        *,
        low: float = -1.0,
        high: float = 1.0,
        normalise: bool = True,
        max_weight: float = 1.0,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.n_assets = int(n_assets)
        self.low = float(low)
        self.high = float(high)
        self.normalise = bool(normalise)
        self.max_weight = float(max_weight)

    def gym_space(self) -> spaces.Space:
        return spaces.Box(low=self.low, high=self.high, shape=(self.n_assets,), dtype=np.float32)

    def transform(self, raw_action: Any) -> np.ndarray:
        a = np.asarray(raw_action, dtype=np.float32).flatten()
        if a.size != self.n_assets:
            a = np.resize(a, (self.n_assets,)).astype(np.float32)
        a = np.clip(a, self.low, self.high)
        a = np.clip(a, -self.max_weight, self.max_weight)
        if self.normalise:
            total = float(np.sum(np.abs(a)))
            if total > 1.0:
                a = a / total
        return a.astype(np.float32, copy=False)


class SoftmaxWeightsAction(BaseActionSpace):
    """Simplex weights via softmax — full investment, no cash slice.

    Mirrors FinRL's ``StockPortfolioEnv`` which softmax-normalises the
    raw policy output to a probability vector summing to 1.
    """

    rl_alias: ClassVar[str] = "SoftmaxWeightsAction"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "continuous"

    def __init__(self, n_assets: int, *, name: str | None = None) -> None:
        super().__init__(name=name)
        self.n_assets = int(n_assets)

    def gym_space(self) -> spaces.Space:
        return spaces.Box(low=0.0, high=1.0, shape=(self.n_assets,), dtype=np.float32)

    def transform(self, raw_action: Any) -> np.ndarray:
        a = np.asarray(raw_action, dtype=np.float32).flatten()
        if a.size != self.n_assets:
            a = np.resize(a, (self.n_assets,)).astype(np.float32)
        a = np.clip(a, 0.0, 1.0)
        total = float(np.sum(a))
        if total > 1e-9:
            return (a / total).astype(np.float32, copy=False)
        return (np.ones(self.n_assets, dtype=np.float32) / max(self.n_assets, 1))


class IntegerSharesAction(BaseActionSpace):
    """FinRL ``hmax``-style integer share trades in ``[-hmax, +hmax]``.

    Converts ``Box(-1, 1, (n_assets,))`` into integer share deltas by
    scaling with ``hmax`` and rounding. Used by FinRL's pandas
    ``StockTradingEnv``.
    """

    rl_alias: ClassVar[str] = "IntegerSharesAction"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "discrete-mixed"

    def __init__(self, n_assets: int, *, hmax: int = 100, name: str | None = None) -> None:
        super().__init__(name=name)
        self.n_assets = int(n_assets)
        self.hmax = int(hmax)

    def gym_space(self) -> spaces.Space:
        return spaces.Box(low=-1.0, high=1.0, shape=(self.n_assets,), dtype=np.float32)

    def transform(self, raw_action: Any) -> np.ndarray:
        a = np.asarray(raw_action, dtype=np.float32).flatten()
        if a.size != self.n_assets:
            a = np.resize(a, (self.n_assets,)).astype(np.float32)
        a = np.clip(a, -1.0, 1.0)
        return (a * self.hmax).astype(np.int64, copy=False)


class DiscreteBuySellHoldAction(BaseActionSpace):
    """Single-asset discrete ``{0=hold, 1=buy, 2=sell}`` (FinRL NeurIPS style)."""

    rl_alias: ClassVar[str] = "DiscreteBuySellHoldAction"
    rl_source: ClassVar[str] = "finrl"
    rl_category: ClassVar[str] = "discrete"

    HOLD = 0
    BUY = 1
    SELL = 2

    def gym_space(self) -> spaces.Space:
        return spaces.Discrete(3)

    def transform(self, raw_action: Any) -> int:
        return int(np.asarray(raw_action).flatten()[0])


class MultiDiscreteAction(BaseActionSpace):
    """One discrete action per asset (e.g. ``MultiDiscrete([3, 3, 3])``)."""

    rl_alias: ClassVar[str] = "MultiDiscreteAction"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "discrete"

    def __init__(self, *, nvec: list[int], name: str | None = None) -> None:
        super().__init__(name=name)
        self.nvec = list(int(n) for n in nvec)

    def gym_space(self) -> spaces.Space:
        return spaces.MultiDiscrete(self.nvec)

    def transform(self, raw_action: Any) -> np.ndarray:
        return np.asarray(raw_action, dtype=np.int64)


class TargetPositionAction(BaseActionSpace):
    """Target signed position in ``[-1, 1]`` per asset (long/short)."""

    rl_alias: ClassVar[str] = "TargetPositionAction"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "continuous"

    def __init__(self, n_assets: int, *, leverage: float = 1.0, name: str | None = None) -> None:
        super().__init__(name=name)
        self.n_assets = int(n_assets)
        self.leverage = float(leverage)

    def gym_space(self) -> spaces.Space:
        return spaces.Box(low=-1.0, high=1.0, shape=(self.n_assets,), dtype=np.float32)

    def transform(self, raw_action: Any) -> np.ndarray:
        a = np.asarray(raw_action, dtype=np.float32).flatten()
        if a.size != self.n_assets:
            a = np.resize(a, (self.n_assets,)).astype(np.float32)
        return np.clip(a, -1.0, 1.0) * self.leverage


__all__ = [
    "BaseActionSpace",
    "ContinuousWeightsAction",
    "DiscreteBuySellHoldAction",
    "IntegerSharesAction",
    "MultiDiscreteAction",
    "SoftmaxWeightsAction",
    "TargetPositionAction",
]
