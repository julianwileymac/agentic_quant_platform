"""``PrioritizedReplayBuffer`` — Schaul et al. ICLR 2016 PER.

Sum-tree backed prioritised experience replay. Probability of
sampling transition ``i`` is::

    P(i) = p_i^α / Σ p_j^α

with ``p_i = |TD_error_i| + ε`` (rank-free, proportional variant).
Importance-sampling correction weights ``w_i = (N · P(i))^{−β}`` are
returned alongside the batch so the optimiser can multiply the
per-sample loss by ``w_i`` to remove the bias.

``β`` is annealed from ``beta_start`` (default 0.4) to ``beta_end``
(default 1.0) linearly over ``beta_anneal_steps`` updates.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

import numpy as np

from aqp_rl.core.replay import BaseReplayBuffer

logger = logging.getLogger(__name__)


class _SumTree:
    """Binary sum-tree with per-leaf priority + traversal helpers.

    Supports O(log N) ``update`` and ``retrieve``. Length-``capacity``
    leaves; ``2 · capacity − 1`` total nodes (perfectly balanced).
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self.tree = np.zeros(2 * self.capacity - 1, dtype=np.float64)
        self.data: list[Any | None] = [None] * self.capacity
        self.write = 0
        self.n_entries = 0

    @property
    def total(self) -> float:
        return float(self.tree[0])

    def _propagate(self, idx: int, change: float) -> None:
        parent = (idx - 1) // 2
        self.tree[parent] += change
        if parent != 0:
            self._propagate(parent, change)

    def _retrieve(self, idx: int, s: float) -> int:
        left = 2 * idx + 1
        right = left + 1
        if left >= len(self.tree):
            return idx
        if s <= self.tree[left]:
            return self._retrieve(left, s)
        return self._retrieve(right, s - self.tree[left])

    def add(self, priority: float, data: Any) -> None:
        idx = self.write + self.capacity - 1
        self.data[self.write] = data
        self.update(idx, priority)
        self.write = (self.write + 1) % self.capacity
        self.n_entries = min(self.n_entries + 1, self.capacity)

    def update(self, idx: int, priority: float) -> None:
        change = float(priority) - float(self.tree[idx])
        self.tree[idx] = float(priority)
        self._propagate(idx, change)

    def get(self, s: float) -> tuple[int, float, Any]:
        idx = self._retrieve(0, s)
        data_idx = idx - self.capacity + 1
        return idx, float(self.tree[idx]), self.data[data_idx]


class PrioritizedReplayBuffer(BaseReplayBuffer):
    """Proportional-PER sum-tree buffer (Schaul ICLR 2016)."""

    def __init__(
        self,
        *,
        capacity: int,
        alpha: float = 0.6,
        beta_start: float = 0.4,
        beta_end: float = 1.0,
        beta_anneal_steps: int = 100_000,
        epsilon: float = 1e-6,
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be ≥ 1; got {capacity!r}")
        if not 0.0 <= alpha <= 1.0:
            raise ValueError(f"alpha must be in [0, 1]; got {alpha!r}")
        if not 0.0 <= beta_start <= beta_end <= 1.0:
            raise ValueError("beta_start must be ≤ beta_end ≤ 1.0")
        if beta_anneal_steps < 1:
            raise ValueError(f"beta_anneal_steps must be ≥ 1; got {beta_anneal_steps!r}")
        if epsilon <= 0:
            raise ValueError(f"epsilon must be > 0; got {epsilon!r}")
        self.capacity = int(capacity)
        self.alpha = float(alpha)
        self.beta_start = float(beta_start)
        self.beta_end = float(beta_end)
        self.beta_anneal_steps = int(beta_anneal_steps)
        self.epsilon = float(epsilon)
        self._tree = _SumTree(self.capacity)
        self._max_priority = 1.0
        self._sample_steps = 0

    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool,
        info: Mapping[str, Any] | None = None,
    ) -> None:
        payload = {
            "obs": obs,
            "action": action,
            "reward": float(reward),
            "next_obs": next_obs,
            "done": bool(done),
            "info": dict(info or {}),
        }
        priority = (self._max_priority + self.epsilon) ** self.alpha
        self._tree.add(priority, payload)

    def sample(self, batch_size: int) -> dict[str, Any]:
        n = min(int(batch_size), len(self))
        if n == 0:
            return {
                "obs": [],
                "action": [],
                "reward": [],
                "next_obs": [],
                "done": [],
                "info": [],
                "weights": np.empty(0, dtype=np.float64),
                "indices": np.empty(0, dtype=np.int64),
            }
        total = self._tree.total
        segment = total / n
        batch: list[Any] = []
        indices = np.empty(n, dtype=np.int64)
        priorities = np.empty(n, dtype=np.float64)
        for i in range(n):
            a = i * segment
            b = (i + 1) * segment
            s = float(np.random.uniform(a, b))
            tree_idx, priority, data = self._tree.get(s)
            indices[i] = tree_idx
            priorities[i] = priority
            batch.append(data)
        beta = self._current_beta()
        self._sample_steps += 1
        # Importance-sampling weights.
        sampling_probs = priorities / max(total, 1e-12)
        weights = (len(self) * sampling_probs) ** (-beta)
        weights = weights / max(weights.max(), 1e-12)
        return {
            "obs": [b["obs"] for b in batch],
            "action": [b["action"] for b in batch],
            "reward": [b["reward"] for b in batch],
            "next_obs": [b["next_obs"] for b in batch],
            "done": [b["done"] for b in batch],
            "info": [b["info"] for b in batch],
            "weights": weights,
            "indices": indices,
        }

    def update_priorities(self, indices: np.ndarray, td_errors: np.ndarray) -> None:
        """Update per-sample priorities after a gradient step."""
        if len(indices) != len(td_errors):
            raise ValueError(
                f"indices ({len(indices)}) and td_errors ({len(td_errors)}) length mismatch"
            )
        for tree_idx, td in zip(indices, td_errors, strict=False):
            p = (abs(float(td)) + self.epsilon) ** self.alpha
            self._tree.update(int(tree_idx), p)
            self._max_priority = max(self._max_priority, float(abs(float(td)) + self.epsilon))

    def _current_beta(self) -> float:
        frac = min(1.0, self._sample_steps / self.beta_anneal_steps)
        return float(self.beta_start + (self.beta_end - self.beta_start) * frac)

    def __len__(self) -> int:
        return self._tree.n_entries


__all__ = ["PrioritizedReplayBuffer"]
