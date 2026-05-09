"""Replay buffers + trajectory store contracts.

:class:`BaseReplayBuffer` is the in-memory experience replay used by
off-policy algorithms (DQN / SAC / TD3). :class:`BaseTrajectoryStore` is
the persistence layer — concrete implementations write per-step records
to Iceberg via :func:`aqp.data.iceberg_catalog.append_arrow` so the UI
can replay episodes step-by-step from durable storage.
"""
from __future__ import annotations

import logging
from abc import abstractmethod
from collections import deque
from typing import Any, ClassVar, Iterable, Mapping

from aqp.rl.core.base import RL_KIND_TRAJECTORY_STORE, RLComponent

logger = logging.getLogger(__name__)


class BaseReplayBuffer:
    """Abstract experience replay buffer (in-memory)."""

    @abstractmethod
    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool,
        info: Mapping[str, Any] | None = None,
    ) -> None:  # pragma: no cover - abstract
        ...

    @abstractmethod
    def sample(self, batch_size: int) -> dict[str, Any]:  # pragma: no cover - abstract
        ...

    @abstractmethod
    def __len__(self) -> int:  # pragma: no cover - abstract
        ...


class InMemoryReplayBuffer(BaseReplayBuffer):
    """Bounded FIFO experience replay (deque-backed).

    Suitable for small Q-family / actor-critic experiments. Production-grade
    off-policy training should use SB3 / RLlib's prioritised replay; this
    is a pure-Python reference for the in-house agents.
    """

    def __init__(self, capacity: int = 100_000) -> None:
        self.capacity = int(capacity)
        self._buf: deque[dict[str, Any]] = deque(maxlen=self.capacity)

    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool,
        info: Mapping[str, Any] | None = None,
    ) -> None:
        self._buf.append(
            {
                "obs": obs,
                "action": action,
                "reward": float(reward),
                "next_obs": next_obs,
                "done": bool(done),
                "info": dict(info or {}),
            }
        )

    def sample(self, batch_size: int) -> dict[str, Any]:
        import random

        n = min(int(batch_size), len(self._buf))
        if n == 0:
            return {"obs": [], "action": [], "reward": [], "next_obs": [], "done": []}
        sample = random.sample(self._buf, n)
        return {
            "obs": [s["obs"] for s in sample],
            "action": [s["action"] for s in sample],
            "reward": [s["reward"] for s in sample],
            "next_obs": [s["next_obs"] for s in sample],
            "done": [s["done"] for s in sample],
            "info": [s["info"] for s in sample],
        }

    def __len__(self) -> int:
        return len(self._buf)


class BaseTrajectoryStore(RLComponent):
    """Abstract trajectory store: persists per-step records for replay.

    Concrete implementations:

    - :class:`aqp.rl.trajectories.iceberg_writer.IcebergTrajectoryStore` —
      Iceberg-backed (default). Buffers Arrow rows in memory and flushes
      to ``rl.trajectories`` / ``rl.equity_curves`` /
      ``rl.action_logs`` / ``rl.reward_decomposition`` via
      :func:`aqp.data.iceberg_catalog.append_arrow`.
    - :class:`InMemoryTrajectoryStore` (below) — for unit tests and
      local-only runs.
    """

    __abstract_rl__: ClassVar[bool] = True
    rl_kind: ClassVar[str] = RL_KIND_TRAJECTORY_STORE

    @abstractmethod
    def append_step(self, record: Mapping[str, Any]) -> None:  # pragma: no cover - abstract
        """Buffer a single per-step record."""

    @abstractmethod
    def append_equity(self, record: Mapping[str, Any]) -> None:  # pragma: no cover - abstract
        """Buffer a single equity-curve record."""

    @abstractmethod
    def append_action(self, record: Mapping[str, Any]) -> None:  # pragma: no cover - abstract
        """Buffer a single action-log record."""

    @abstractmethod
    def append_reward_decomposition(
        self, records: Iterable[Mapping[str, Any]]
    ) -> None:  # pragma: no cover - abstract
        """Buffer one or more reward-decomposition rows for the current step."""

    @abstractmethod
    def flush(self) -> None:  # pragma: no cover - abstract
        """Persist all buffered records to the underlying store."""

    def close(self) -> None:
        """Flush and release resources. Default delegates to :meth:`flush`."""
        try:
            self.flush()
        except Exception:  # noqa: BLE001
            logger.exception("trajectory store flush failed during close")


class InMemoryTrajectoryStore(BaseTrajectoryStore):
    """Trajectory store that keeps everything in Python lists.

    Used by the unit tests and the API ``/rl/lab/preview-*`` endpoints
    (which never want to commit to Iceberg).
    """

    rl_alias: ClassVar[str] = "InMemoryTrajectoryStore"
    rl_source: ClassVar[str] = "aqp"
    rl_tags: ClassVar[tuple[str, ...]] = ("memory",)

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.equity: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.reward_terms: list[dict[str, Any]] = []

    def append_step(self, record: Mapping[str, Any]) -> None:
        self.steps.append(dict(record))

    def append_equity(self, record: Mapping[str, Any]) -> None:
        self.equity.append(dict(record))

    def append_action(self, record: Mapping[str, Any]) -> None:
        self.actions.append(dict(record))

    def append_reward_decomposition(self, records: Iterable[Mapping[str, Any]]) -> None:
        for r in records:
            self.reward_terms.append(dict(r))

    def flush(self) -> None:
        return None


__all__ = [
    "BaseReplayBuffer",
    "BaseTrajectoryStore",
    "InMemoryReplayBuffer",
    "InMemoryTrajectoryStore",
]
