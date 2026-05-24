"""Policy + agent base classes — the training/eval lifecycle contract.

:class:`BasePolicy` represents the parameterised policy itself
(``predict(obs) -> action``); :class:`BaseRLAgent` wraps a policy with a
training algorithm so the runtime can drive ``build → train → predict →
save / load`` uniformly across SB3 / ElegantRL / Ray RLlib / CleanRL /
classical / Q-family / actor-critic / evolutionary trees.
"""
from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym

from aqp_rl.core.base import RL_KIND_AGENT, RL_KIND_POLICY, RLComponent


class BasePolicy(RLComponent):
    """Stateless policy: ``predict(obs, deterministic=True) -> action``."""

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_POLICY

    @abstractmethod
    def predict(
        self,
        obs: Any,
        *,
        deterministic: bool = True,
    ) -> Any:  # pragma: no cover - abstract
        """Return an action from the policy."""

    def reset(self) -> None:
        """Reset any recurrent state at episode boundary."""


class BaseRLAgent(RLComponent):
    """Training-aware agent: orchestrates the policy + algorithm.

    Concrete subclasses (e.g. :class:`SB3Adapter`,
    :class:`ElegantRLAdapter`, :class:`RayRLlibAdapter`,
    :class:`CleanRLAdapter`, :class:`LLMHybridAgent`) wrap a third-party
    library (or hand-coded loop) into the
    ``build → train → save / load → predict`` contract used by
    :class:`aqp_rl.runtime.RLRuntime`.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_AGENT

    #: Short identifier for the algorithm — surfaces in MLflow run name and
    #: ``rl_runs`` rows. Subclasses set this from their ``algorithm`` kwarg.
    algorithm: str = "abstract"

    @abstractmethod
    def build(self, env: gym.Env) -> None:  # pragma: no cover - abstract
        """Materialise the underlying model / network for ``env``."""

    @abstractmethod
    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:  # pragma: no cover - abstract
        """Run the training loop for ``total_timesteps`` steps."""

    @abstractmethod
    def predict(
        self,
        obs: Any,
        *,
        deterministic: bool = True,
    ) -> Any:  # pragma: no cover - abstract
        """Sample an action for inference / rollout."""

    @abstractmethod
    def save(self, path: str | Path) -> Path:  # pragma: no cover - abstract
        """Persist the agent / policy to ``path``. Returns the canonical path."""

    @abstractmethod
    def load(
        self,
        path: str | Path,
        env: gym.Env | None = None,
    ) -> None:  # pragma: no cover - abstract
        """Load the agent / policy from ``path`` (optionally rebinding ``env``)."""

    @property
    def model(self) -> Any:
        """Concrete underlying model (third-party object). May be ``None`` until built."""
        return getattr(self, "_model", None)


__all__ = [
    "BasePolicy",
    "BaseRLAgent",
]
