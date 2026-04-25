"""Neuro-evolution with novelty search.

Scores each individual by how far its behavioural signature is from the
k-nearest archive entries, rather than purely by reward. Encourages
exploration in sparse-reward environments.
"""
from __future__ import annotations

from typing import Callable

import numpy as np

from aqp.core.registry import agent
from aqp.rl.agents.evolutionary.neuro import NeuroEvolutionAgent


def _behaviour(vec: list[int], bins: int = 8) -> np.ndarray:
    if not vec:
        return np.zeros(bins, dtype=float)
    arr = np.asarray(vec, dtype=int)
    hist, _ = np.histogram(arr, bins=bins, range=(0, bins))
    total = hist.sum()
    return hist / total if total > 0 else hist.astype(float)


@agent("NeuroEvolutionNoveltyAgent", tags=("rl", "evolutionary", "novelty-search"))
class NeuroEvolutionNoveltyAgent(NeuroEvolutionAgent):
    def __init__(
        self,
        *args,
        archive_size: int = 256,
        k_neighbors: int = 5,
        novelty_weight: float = 0.5,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.archive_size = int(archive_size)
        self.k_neighbors = int(k_neighbors)
        self.novelty_weight = float(novelty_weight)
        self.archive: list[np.ndarray] = []

    def _rollout_with_behaviour(self, env, theta: np.ndarray, max_steps: int = 2_000) -> tuple[float, np.ndarray]:
        obs, _ = env.reset()
        total = 0.0
        actions: list[int] = []
        for _ in range(max_steps):
            a = self._forward(np.asarray(obs, dtype=np.float32), theta)
            actions.append(int(a))
            obs, reward, terminated, truncated, _info = env.step(a)
            total += float(reward)
            if bool(terminated) or bool(truncated):
                break
        return total, _behaviour(actions, bins=max(self.n_actions, 2))

    def _novelty(self, behaviour: np.ndarray) -> float:
        if not self.archive:
            return 1.0
        arr = np.stack(self.archive)
        dists = np.linalg.norm(arr - behaviour, axis=1)
        k = min(self.k_neighbors, len(dists))
        nearest = np.sort(dists)[:k]
        return float(nearest.mean()) if k else 0.0

    def train_on_env(
        self,
        env_factory: Callable[[], object],
        generations: int = 50,
        max_steps: int = 2_000,
    ) -> list[float]:
        history: list[float] = []
        for _ in range(generations):
            scores = np.zeros(self.population, dtype=np.float64)
            behaviours: list[np.ndarray] = []
            rewards: list[float] = []
            for k, theta in enumerate(self.pop):
                r, beh = self._rollout_with_behaviour(env_factory(), theta, max_steps=max_steps)
                rewards.append(r)
                behaviours.append(beh)
                nov = self._novelty(beh)
                scores[k] = r + self.novelty_weight * nov
            elite_idx = np.argsort(scores)[-self.elite :]
            elites = self.pop[elite_idx]
            self.best = elites[-1]
            # Add winners' behaviours to the archive with LRU trimming.
            for idx in elite_idx:
                self.archive.append(behaviours[idx])
            if len(self.archive) > self.archive_size:
                self.archive = self.archive[-self.archive_size :]
            # Reproduce.
            new_pop: list[np.ndarray] = list(elites)
            while len(new_pop) < self.population:
                a, b = self.rng.choice(self.elite, size=2, replace=False)
                mask = self.rng.random(self.n_params) < 0.5
                child = np.where(mask, elites[a], elites[b])
                child = child + self.rng.normal(size=child.shape) * self.mutation_sigma
                new_pop.append(child)
            self.pop = np.stack(new_pop[: self.population])
            history.append(float(np.max(rewards)))
        return history


__all__ = ["NeuroEvolutionNoveltyAgent"]
