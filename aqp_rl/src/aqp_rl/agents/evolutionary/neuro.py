"""Neuro-evolution — population of MLP policies with crossover + mutation."""
from __future__ import annotations

from typing import Callable

import numpy as np

from aqp.core.registry import agent


@agent("NeuroEvolutionAgent", tags=("rl", "evolutionary", "neuro-evolution"))
class NeuroEvolutionAgent:
    def __init__(
        self,
        state_dim: int,
        n_actions: int,
        hidden: int = 32,
        population: int = 32,
        elite: int = 4,
        mutation_sigma: float = 0.05,
        seed: int = 42,
    ) -> None:
        self.state_dim = int(state_dim)
        self.n_actions = int(n_actions)
        self.hidden = int(hidden)
        self.population = int(population)
        self.elite = int(elite)
        self.mutation_sigma = float(mutation_sigma)
        self.rng = np.random.default_rng(seed)

        self.n_params = state_dim * hidden + hidden + hidden * n_actions + n_actions
        self.pop = self.rng.normal(size=(population, self.n_params)) * 0.1
        self.best = self.pop[0]

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
        return int(np.argmax(h @ w2 + b2))

    def act(self, obs: np.ndarray, greedy: bool = True) -> int:
        return self._forward(np.asarray(obs, dtype=np.float32), self.best)

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
            fitness = np.array(
                [self._rollout(env_factory(), ind, max_steps=max_steps) for ind in self.pop]
            )
            elite_idx = np.argsort(fitness)[-self.elite :]
            elites = self.pop[elite_idx]
            self.best = elites[-1]
            new_pop: list[np.ndarray] = list(elites)
            while len(new_pop) < self.population:
                a, b = self.rng.choice(self.elite, size=2, replace=False)
                mask = self.rng.random(self.n_params) < 0.5
                child = np.where(mask, elites[a], elites[b])
                child = child + self.rng.normal(size=child.shape) * self.mutation_sigma
                new_pop.append(child)
            self.pop = np.stack(new_pop[: self.population])
            history.append(float(fitness.max()))
        return history


__all__ = ["NeuroEvolutionAgent"]
