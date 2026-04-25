"""Vanilla on-policy Actor-Critic agent (A2C-style, single env)."""
from __future__ import annotations

from typing import Any

import numpy as np

from aqp.core.registry import agent


def _import_torch() -> Any:
    try:
        import torch
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "torch is required for actor-critic agents. Install the `ml-torch` extra."
        ) from exc
    return torch


def _build_ac(torch: Any, state_dim: int, n_actions: int, hidden: int, duel: bool = False, recurrent: bool = False):
    nn = torch.nn

    class _ActorCritic(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            if recurrent:
                self.encoder = nn.LSTM(state_dim, hidden, batch_first=True)
            else:
                self.encoder = nn.Sequential(nn.Linear(state_dim, hidden), nn.ReLU())
            self.policy_head = nn.Linear(hidden, n_actions)
            if duel:
                self.value_stream = nn.Linear(hidden, hidden)
                self.value_head = nn.Linear(hidden, 1)
            else:
                self.value_head = nn.Linear(hidden, 1)

        def encode(self, x):
            if recurrent:
                if x.dim() == 2:
                    x = x.unsqueeze(1)
                out, _ = self.encoder(x)
                return out[:, -1, :]
            return self.encoder(x)

        def forward(self, x):
            h = self.encode(x)
            logits = self.policy_head(h)
            value = self.value_head(
                torch.relu(self.value_stream(h)) if duel else h
            ) if duel else self.value_head(h)
            return logits, value.squeeze(-1)

    return _ActorCritic()


@agent("ActorCriticAgent", tags=("rl", "actor-critic", "a2c"))
class ActorCriticAgent:
    """Plain A2C with entropy bonus."""

    duel: bool = False
    recurrent: bool = False
    name: str = "ac"

    def __init__(
        self,
        state_dim: int,
        n_actions: int,
        hidden_size: int = 64,
        lr: float = 3e-4,
        gamma: float = 0.99,
        entropy_coef: float = 0.01,
        value_coef: float = 0.5,
        device: str = "cpu",
        seed: int = 42,
    ) -> None:
        torch = _import_torch()
        torch.manual_seed(seed)
        self.state_dim = int(state_dim)
        self.n_actions = int(n_actions)
        self.gamma = float(gamma)
        self.entropy_coef = float(entropy_coef)
        self.value_coef = float(value_coef)
        self.device = device
        self.net = _build_ac(
            torch, state_dim, n_actions, hidden_size, duel=self.duel, recurrent=self.recurrent
        ).to(device)
        self.optim = torch.optim.Adam(self.net.parameters(), lr=lr)

    def act(self, state, greedy: bool = False) -> tuple[int, Any]:
        torch = _import_torch()
        x = torch.tensor(np.asarray(state, dtype=np.float32)).unsqueeze(0).to(self.device)
        logits, value = self.net(x)
        probs = torch.softmax(logits, dim=-1)
        if greedy:
            action = int(probs.argmax(dim=-1).item())
        else:
            dist = torch.distributions.Categorical(probs=probs)
            action = int(dist.sample().item())
        log_prob = torch.log(probs.squeeze(0)[action] + 1e-8)
        return action, (log_prob, value.squeeze(0))

    def train_on_env(self, env, episodes: int = 50, max_steps: int | None = None) -> list[float]:
        torch = _import_torch()
        returns: list[float] = []
        for _ in range(episodes):
            obs, _ = env.reset()
            log_probs, values, rewards_list, entropies = [], [], [], []
            done = False
            step = 0
            while not done:
                action, aux = self.act(obs)
                log_prob, value = aux
                next_obs, reward, terminated, truncated, _info = env.step(action)
                done = bool(terminated) or bool(truncated)
                log_probs.append(log_prob)
                values.append(value)
                rewards_list.append(float(reward))
                # Entropy for exploration bonus
                probs = torch.softmax(self.net(torch.tensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0).to(self.device))[0], dim=-1)
                entropies.append(-(probs * torch.log(probs + 1e-8)).sum())
                obs = next_obs
                step += 1
                if max_steps is not None and step >= max_steps:
                    break

            R = 0.0
            disc: list[float] = []
            for r in reversed(rewards_list):
                R = r + self.gamma * R
                disc.insert(0, R)
            disc_t = torch.tensor(disc, dtype=torch.float32).to(self.device)
            values_t = torch.stack(values)
            log_probs_t = torch.stack(log_probs)
            entropy_t = torch.stack(entropies).mean() if entropies else torch.tensor(0.0)
            advantage = disc_t - values_t.detach()
            policy_loss = -(log_probs_t * advantage).mean()
            value_loss = torch.nn.functional.mse_loss(values_t, disc_t)
            loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy_t
            self.optim.zero_grad()
            loss.backward()
            self.optim.step()
            returns.append(float(sum(rewards_list)))
        return returns


__all__ = ["ActorCriticAgent"]
