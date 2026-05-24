"""Base Q-learning agent with a pluggable network factory.

The agent interacts with any ``gymnasium.Env`` exposing a
``Discrete(n)`` action space. Observations are expected to be flat
vectors (or 2-D ``(T, F)`` for the recurrent variants).

The replay buffer, epsilon-greedy loop, and target-network update logic
live here; concrete variants only override :meth:`_build_network` and,
if they need it, :meth:`_q_target`.
"""
from __future__ import annotations

import logging
import random
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Transition:
    state: np.ndarray
    action: int
    reward: float
    next_state: np.ndarray
    done: bool


def _import_torch() -> Any:
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "torch is required for Q-family agents. Install the `ml-torch` extra."
        ) from exc
    return torch


class BaseQAgent:
    """DQN baseline. Subclasses override :meth:`_build_network`."""

    name: str = "q-base"
    recurrent: bool = False

    def __init__(
        self,
        state_dim: int,
        n_actions: int,
        hidden_size: int = 64,
        lr: float = 1e-3,
        gamma: float = 0.99,
        buffer_size: int = 10_000,
        batch_size: int = 32,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.05,
        epsilon_decay: int = 1_000,
        target_update: int = 200,
        device: str = "cpu",
        seed: int = 42,
    ) -> None:
        self.state_dim = int(state_dim)
        self.n_actions = int(n_actions)
        self.hidden_size = int(hidden_size)
        self.lr = float(lr)
        self.gamma = float(gamma)
        self.buffer_size = int(buffer_size)
        self.batch_size = int(batch_size)
        self.epsilon_start = float(epsilon_start)
        self.epsilon_end = float(epsilon_end)
        self.epsilon_decay = int(epsilon_decay)
        self.target_update = int(target_update)
        self.device = device
        self.seed = int(seed)

        torch = _import_torch()
        torch.manual_seed(seed)
        random.seed(seed)

        self.q_net = self._build_network(torch)
        self.target_net = self._build_network(torch)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.optimiser = torch.optim.Adam(self.q_net.parameters(), lr=self.lr)

        self.replay: deque[Transition] = deque(maxlen=self.buffer_size)
        self._global_step = 0
        self._losses: list[float] = []

    # ---- overridable hooks --------------------------------------------

    def _build_network(self, torch: Any) -> Any:
        nn = torch.nn

        class _MLP(nn.Module):
            def __init__(self, in_dim: int, hidden: int, out_dim: int) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Linear(in_dim, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, hidden),
                    nn.ReLU(),
                    nn.Linear(hidden, out_dim),
                )

            def forward(self, x):
                return self.net(x)

        return _MLP(self.state_dim, self.hidden_size, self.n_actions).to(self.device)

    def _q_target(self, torch: Any, rewards, next_states, dones) -> Any:
        with torch.no_grad():
            next_q = self.target_net(next_states).max(dim=1)[0]
            return rewards + self.gamma * next_q * (1 - dones)

    # ---- action + learn -----------------------------------------------

    def epsilon(self) -> float:
        frac = min(1.0, self._global_step / self.epsilon_decay)
        return self.epsilon_start + frac * (self.epsilon_end - self.epsilon_start)

    def act(self, state: np.ndarray, greedy: bool = False) -> int:
        torch = _import_torch()
        if not greedy and random.random() < self.epsilon():
            return random.randint(0, self.n_actions - 1)
        with torch.no_grad():
            state_t = torch.tensor(np.asarray(state, dtype=np.float32)).unsqueeze(0).to(self.device)
            q_values = self.q_net(state_t)
            return int(q_values.argmax(dim=1).item())

    def remember(self, *, state, action, reward, next_state, done) -> None:
        self.replay.append(
            Transition(
                state=np.asarray(state, dtype=np.float32),
                action=int(action),
                reward=float(reward),
                next_state=np.asarray(next_state, dtype=np.float32),
                done=bool(done),
            )
        )

    def learn(self) -> float | None:
        if len(self.replay) < self.batch_size:
            return None
        torch = _import_torch()
        batch = random.sample(self.replay, self.batch_size)
        states = torch.tensor(np.stack([t.state for t in batch]), dtype=torch.float32).to(self.device)
        actions = torch.tensor([t.action for t in batch], dtype=torch.long).to(self.device)
        rewards = torch.tensor([t.reward for t in batch], dtype=torch.float32).to(self.device)
        next_states = torch.tensor(np.stack([t.next_state for t in batch]), dtype=torch.float32).to(self.device)
        dones = torch.tensor([t.done for t in batch], dtype=torch.float32).to(self.device)

        q_values = self.q_net(states).gather(1, actions.unsqueeze(1)).squeeze(1)
        target_q = self._q_target(torch, rewards, next_states, dones)
        loss = torch.nn.functional.mse_loss(q_values, target_q)

        self.optimiser.zero_grad()
        loss.backward()
        self.optimiser.step()

        self._global_step += 1
        if self._global_step % self.target_update == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())
        self._losses.append(float(loss.item()))
        return float(loss.item())

    # ---- full loop ----------------------------------------------------

    def train_on_env(self, env, episodes: int = 50, max_steps: int | None = None) -> list[float]:
        returns: list[float] = []
        for ep in range(episodes):
            obs, _ = env.reset()
            total = 0.0
            step = 0
            done = False
            while not done:
                action = self.act(obs)
                next_obs, reward, terminated, truncated, _info = env.step(action)
                done = bool(terminated) or bool(truncated)
                self.remember(
                    state=obs, action=action, reward=reward, next_state=next_obs, done=done
                )
                self.learn()
                obs = next_obs
                total += float(reward)
                step += 1
                if max_steps is not None and step >= max_steps:
                    break
            returns.append(total)
        return returns


__all__ = ["BaseQAgent", "Transition"]
