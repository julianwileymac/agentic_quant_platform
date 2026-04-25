"""OpenAI-style Evolution Strategies for a dense policy."""
from __future__ import annotations

from typing import Callable

import numpy as np

from aqp.core.registry import agent


@agent("EvolutionStrategyAgent", tags=("rl", "evolutionary", "es"))
class EvolutionStrategyAgent:
    """Two-layer MLP policy trained via ES (Salimans et al., 2017)."""

    def __init__(
        self,
        state_dim: int,
        n_actions: int,
        hidden: int = 32,
        population: int = 32,
        sigma: float = 0.1,
        lr: float = 0.01,
        seed: int = 42,
    ) -> None:
        self.state_dim = int(state_dim)
        self.n_actions = int(n_actions)
        self.hidden = int(hidden)
        self.population = int(population)
        self.sigma = float(sigma)
        self.lr = float(lr)
        self.rng = np.random.default_rng(seed)

        n_params = state_dim * hidden + hidden + hidden * n_actions + n_actions
        self.theta = self.rng.normal(size=n_params) * 0.1

    def _forward(self, obs: np.ndarray, theta: np.ndarray) -> int:
        i = 0
        w1 = theta[i : i + self.state_dim * self.hidden].reshape(self.state_dim, self.hidden)
        i += self.state_dim * self.hidden
        b1 = theta[i : i + self.hidden]
        i += self.hidden
        w2 = theta[i : i + self.hidden * self.n_actions].reshape(self.hidden, self.n_actions)
        i += self.hidden * self.n_actions
        b2 = theta[i : i + self.n_actions]
        h = np.tanh(obs @ w1 + b1)
        logits = h @ w2 + b2
        return int(np.argmax(logits))

    def act(self, obs: np.ndarray, greedy: bool = True) -> int:
        return self._forward(np.asarray(obs, dtype=np.float32), self.theta)

    def _rollout(self, env, theta: np.ndarray, max_steps: int = 2_000) -> float:
        obs, _ = env.reset()
        total = 0.0
        for _ in range(max_steps):
            a = self._forward(np.asarray(obs, dtype=np.float32), theta)
            obs, reward, terminated, truncated, _info = env.step(a)
            total += float(reward)
            if bool(terminated) or bool(truncated):
                break
        return total

    def train_on_env(
        self,
        env_factory: Callable[[], object],
        generations: int = 50,
        max_steps: int = 2_000,
    ) -> list[float]:
        history: list[float] = []
        for _ in range(generations):
            noises = self.rng.normal(size=(self.population, self.theta.size))
            rewards = np.zeros(self.population, dtype=np.float64)
            for k in range(self.population):
                theta_k = self.theta + self.sigma * noises[k]
                env = env_factory()
                rewards[k] = self._rollout(env, theta_k, max_steps=max_steps)
                try:
                    env.close()
                except Exception:
                    pass
            mean = rewards.mean()
            std = rewards.std() + 1e-8
            advantages = (rewards - mean) / std
            grad = (noises.T @ advantages) / (self.population * self.sigma)
            self.theta += self.lr * grad
            history.append(float(mean))
        return history


__all__ = ["EvolutionStrategyAgent"]
