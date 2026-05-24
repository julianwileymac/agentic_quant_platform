"""``NStepInfoReplayBuffer`` — n-step + info-dict aware replay.

Port of TradeMaster's ``trademaster/utils/replay_buffer.py::ReplayBufferHFT``
into AQP's :class:`BaseReplayBuffer` contract. The buffer accumulates
``n_steps`` of transitions before emitting a single n-step
transition::

    R_n = Σ_{k=0..n-1} γ^k · r_{t+k}
    next_obs = obs at step t+n
    done = any(done[t..t+n-1])

In addition the buffer preserves the per-step ``info`` dict (action
mask, DP_action one-hot, available_action — needed by HFT_DDQN to
apply masked-action loss + DP distillation).
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Mapping

import numpy as np

from aqp_rl.core.replay import BaseReplayBuffer

logger = logging.getLogger(__name__)


class NStepInfoReplayBuffer(BaseReplayBuffer):
    """N-step return buffer with first-step info preservation.

    Parameters
    ----------
    capacity:
        Maximum number of n-step transitions stored.
    n_steps:
        Number of bars to accumulate before emitting an n-step
        transition. Default ``1`` (degenerates to a standard 1-step
        buffer).
    gamma:
        Discount factor applied to the n-step reward accumulation.
        Default ``0.99``.
    info_keys:
        Whitelist of ``info`` keys to preserve (typically
        ``("available_action", "DP_action", "previous_action")`` for
        HFT_DDQN). When ``None``, the full dict is preserved.
    """

    def __init__(
        self,
        *,
        capacity: int = 100_000,
        n_steps: int = 1,
        gamma: float = 0.99,
        info_keys: tuple[str, ...] | None = ("available_action", "DP_action", "previous_action"),
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be ≥ 1; got {capacity!r}")
        if n_steps < 1:
            raise ValueError(f"n_steps must be ≥ 1; got {n_steps!r}")
        if not 0.0 <= gamma <= 1.0:
            raise ValueError(f"gamma must be in [0, 1]; got {gamma!r}")
        self.capacity = int(capacity)
        self.n_steps = int(n_steps)
        self.gamma = float(gamma)
        self.info_keys = info_keys
        self._buffer: deque[dict[str, Any]] = deque(maxlen=self.capacity)
        self._nstep_buffer: deque[dict[str, Any]] = deque(maxlen=self.n_steps)

    def add(
        self,
        obs: Any,
        action: Any,
        reward: float,
        next_obs: Any,
        done: bool,
        info: Mapping[str, Any] | None = None,
    ) -> None:
        info_filtered = self._filter_info(info)
        self._nstep_buffer.append(
            {
                "obs": obs,
                "action": action,
                "reward": float(reward),
                "next_obs": next_obs,
                "done": bool(done),
                "info": info_filtered,
            }
        )
        if len(self._nstep_buffer) < self.n_steps and not done:
            return
        # Accumulate n-step return.
        R = 0.0
        for k, step in enumerate(self._nstep_buffer):
            R += (self.gamma ** k) * step["reward"]
        first = self._nstep_buffer[0]
        last = self._nstep_buffer[-1]
        any_done = any(step["done"] for step in self._nstep_buffer)
        self._buffer.append(
            {
                "obs": first["obs"],
                "action": first["action"],
                "reward": R,
                "next_obs": last["next_obs"],
                "done": any_done,
                "info": first["info"],
                "n_steps": len(self._nstep_buffer),
            }
        )
        if done:
            # Flush remaining shorter accumulations.
            while len(self._nstep_buffer) > 1:
                self._nstep_buffer.popleft()
                R = 0.0
                for k, step in enumerate(self._nstep_buffer):
                    R += (self.gamma ** k) * step["reward"]
                first = self._nstep_buffer[0]
                last = self._nstep_buffer[-1]
                self._buffer.append(
                    {
                        "obs": first["obs"],
                        "action": first["action"],
                        "reward": R,
                        "next_obs": last["next_obs"],
                        "done": True,
                        "info": first["info"],
                        "n_steps": len(self._nstep_buffer),
                    }
                )
            self._nstep_buffer.clear()

    def sample(self, batch_size: int) -> dict[str, Any]:
        import random

        n = min(int(batch_size), len(self._buffer))
        if n == 0:
            return {
                "obs": [],
                "action": [],
                "reward": [],
                "next_obs": [],
                "done": [],
                "info": [],
                "n_steps": [],
            }
        sample = random.sample(self._buffer, n)
        return {
            "obs": [s["obs"] for s in sample],
            "action": [s["action"] for s in sample],
            "reward": [s["reward"] for s in sample],
            "next_obs": [s["next_obs"] for s in sample],
            "done": [s["done"] for s in sample],
            "info": [s["info"] for s in sample],
            "n_steps": [s["n_steps"] for s in sample],
        }

    def __len__(self) -> int:
        return len(self._buffer)

    def _filter_info(self, info: Mapping[str, Any] | None) -> dict[str, Any]:
        if not info:
            return {}
        if self.info_keys is None:
            return dict(info)
        return {k: v for k, v in info.items() if k in self.info_keys}


__all__ = ["NStepInfoReplayBuffer"]
