"""Genuinely-new SPM RL agent ports.

These four are not present in the existing ``q_family`` /
``actor_critic`` / ``evolutionary`` packages.

All implement the minimal :class:`BaseRLAgent`-compatible contract:
``train(env, total_timesteps)`` and ``act(obs)`` (+ ``save`` / ``load``).
The existing :func:`aqp.rl.trainer.train_from_config` happily dispatches
to anything that has these methods.

PyTorch is imported lazily inside class methods so importing this
module is cheap.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

from aqp.core.registry import register

logger = logging.getLogger(__name__)


def _t():
    import torch
    from torch import nn
    return torch, nn


@dataclass
class _AgentDefaults:
    gamma: float = 0.99
    lr: float = 1e-3
    hidden_size: int = 64
    batch_size: int = 32
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay_steps: int = 5000
    replay_capacity: int = 10000
    target_update_freq: int = 500


# ---------------------------------------------------------------------------
# Double + Dueling DQN
# ---------------------------------------------------------------------------


@register("DoubleDuelingDQNAgent", source="stock_prediction_models", category="rl_q", kind="agent")
class DoubleDuelingDQNAgent:
    """Double DQN action selection + dueling Q-network architecture."""

    def __init__(self, **kwargs: Any) -> None:
        self.cfg = _AgentDefaults(**{k: v for k, v in kwargs.items() if hasattr(_AgentDefaults, k)})
        self.online: Any = None
        self.target: Any = None
        self.optimizer: Any = None
        self.replay: deque = deque(maxlen=self.cfg.replay_capacity)
        self._steps = 0
        self.action_dim: int = 0

    def _build(self, obs_dim: int, action_dim: int):
        torch, nn = _t()
        self.action_dim = action_dim

        class _DuelingNet(nn.Module):
            def __init__(self, obs_dim: int, action_dim: int, hidden: int):
                super().__init__()
                self.shared = nn.Sequential(nn.Linear(obs_dim, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU())
                self.value = nn.Linear(hidden, 1)
                self.advantage = nn.Linear(hidden, action_dim)

            def forward(self, x):
                features = self.shared(x)
                v = self.value(features)
                a = self.advantage(features)
                return v + a - a.mean(dim=-1, keepdim=True)

        self.online = _DuelingNet(obs_dim, action_dim, self.cfg.hidden_size)
        self.target = _DuelingNet(obs_dim, action_dim, self.cfg.hidden_size)
        self.target.load_state_dict(self.online.state_dict())
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=self.cfg.lr)

    def _epsilon(self) -> float:
        frac = min(self._steps / max(self.cfg.epsilon_decay_steps, 1), 1.0)
        return self.cfg.epsilon_start + (self.cfg.epsilon_end - self.cfg.epsilon_start) * frac

    def act(self, obs):
        torch, _ = _t()
        if self.online is None or np.random.random() < self._epsilon():
            return int(np.random.randint(max(self.action_dim, 1)))
        with torch.no_grad():
            q = self.online(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
            return int(q.argmax(dim=-1).item())

    def train(self, env, total_timesteps: int) -> dict[str, Any]:
        torch, nn = _t()
        obs, _ = env.reset()
        obs_dim = int(np.asarray(obs).flatten().shape[0])
        action_dim = int(getattr(env.action_space, "n", 1))
        self._build(obs_dim, action_dim)
        loss_fn = nn.MSELoss()
        episode_reward = 0.0
        rewards: list[float] = []
        for step in range(total_timesteps):
            self._steps = step
            action = self.act(np.asarray(obs).flatten())
            next_obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
            self.replay.append((np.asarray(obs).flatten(), action, reward, np.asarray(next_obs).flatten(), float(done)))
            obs = next_obs
            episode_reward += reward
            if done:
                rewards.append(episode_reward)
                episode_reward = 0.0
                obs, _ = env.reset()
            if len(self.replay) >= self.cfg.batch_size:
                batch = [self.replay[i] for i in np.random.choice(len(self.replay), self.cfg.batch_size, replace=False)]
                obs_b, act_b, rew_b, next_b, done_b = (np.array(x) for x in zip(*batch, strict=False))
                obs_t = torch.as_tensor(obs_b, dtype=torch.float32)
                next_t = torch.as_tensor(next_b, dtype=torch.float32)
                act_t = torch.as_tensor(act_b, dtype=torch.long)
                rew_t = torch.as_tensor(rew_b, dtype=torch.float32)
                done_t = torch.as_tensor(done_b, dtype=torch.float32)
                with torch.no_grad():
                    next_actions = self.online(next_t).argmax(dim=-1)
                    next_q = self.target(next_t).gather(1, next_actions.unsqueeze(-1)).squeeze(-1)
                target = rew_t + self.cfg.gamma * next_q * (1 - done_t)
                pred = self.online(obs_t).gather(1, act_t.unsqueeze(-1)).squeeze(-1)
                loss = loss_fn(pred, target)
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
            if step % self.cfg.target_update_freq == 0 and self.online is not None:
                self.target.load_state_dict(self.online.state_dict())
        return {"episode_rewards": rewards, "n_episodes": len(rewards)}

    def save(self, path: str) -> None:
        torch, _ = _t()
        torch.save(self.online.state_dict(), path)

    def load(self, path: str) -> None:
        torch, _ = _t()
        self.online.load_state_dict(torch.load(path))


# ---------------------------------------------------------------------------
# REINFORCE / Policy Gradient
# ---------------------------------------------------------------------------


@register("PolicyGradientAgent", source="stock_prediction_models", category="rl_pg", kind="agent")
class PolicyGradientAgent:
    """REINFORCE with discounted returns."""

    def __init__(self, gamma: float = 0.99, lr: float = 1e-3, hidden_size: int = 64) -> None:
        self.gamma = gamma
        self.lr = lr
        self.hidden_size = hidden_size
        self.policy: Any = None
        self.optimizer: Any = None
        self.action_dim: int = 0

    def _build(self, obs_dim: int, action_dim: int):
        torch, nn = _t()
        self.action_dim = action_dim
        self.policy = nn.Sequential(
            nn.Linear(obs_dim, self.hidden_size), nn.ReLU(),
            nn.Linear(self.hidden_size, action_dim), nn.Softmax(dim=-1),
        )
        self.optimizer = torch.optim.Adam(self.policy.parameters(), lr=self.lr)

    def act(self, obs):
        torch, _ = _t()
        if self.policy is None:
            return int(np.random.randint(max(self.action_dim, 1)))
        with torch.no_grad():
            probs = self.policy(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
            return int(torch.multinomial(probs, 1).item())

    def train(self, env, total_timesteps: int) -> dict[str, Any]:
        torch, _ = _t()
        obs, _ = env.reset()
        obs_dim = int(np.asarray(obs).flatten().shape[0])
        action_dim = int(getattr(env.action_space, "n", 1))
        self._build(obs_dim, action_dim)

        ep_log_probs: list[Any] = []
        ep_rewards: list[float] = []
        all_episode_rewards: list[float] = []
        steps = 0
        while steps < total_timesteps:
            obs_t = torch.as_tensor(np.asarray(obs).flatten(), dtype=torch.float32).unsqueeze(0)
            probs = self.policy(obs_t)
            dist = torch.distributions.Categorical(probs)
            action = dist.sample()
            ep_log_probs.append(dist.log_prob(action))
            obs, reward, terminated, truncated, _ = env.step(int(action.item()))
            ep_rewards.append(reward)
            steps += 1
            if terminated or truncated:
                returns = []
                G = 0.0
                for r in reversed(ep_rewards):
                    G = r + self.gamma * G
                    returns.append(G)
                returns.reverse()
                returns_t = torch.as_tensor(returns, dtype=torch.float32)
                if len(returns_t) > 1:
                    returns_t = (returns_t - returns_t.mean()) / (returns_t.std() + 1e-8)
                loss = -(torch.stack(ep_log_probs).squeeze() * returns_t).sum()
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                all_episode_rewards.append(sum(ep_rewards))
                ep_log_probs = []
                ep_rewards = []
                obs, _ = env.reset()
        return {"episode_rewards": all_episode_rewards, "n_episodes": len(all_episode_rewards)}

    def save(self, path: str) -> None:
        torch, _ = _t()
        torch.save(self.policy.state_dict(), path)

    def load(self, path: str) -> None:
        torch, _ = _t()
        self.policy.load_state_dict(torch.load(path))


# ---------------------------------------------------------------------------
# A3C (single-process A2C variant)
# ---------------------------------------------------------------------------


@register("A3CAgent", source="stock_prediction_models", category="rl_ac", kind="agent")
class A3CAgent:
    """Single-process A2C variant (synchronous A3C)."""

    def __init__(self, gamma: float = 0.99, lr: float = 1e-3, hidden_size: int = 64) -> None:
        self.gamma = gamma
        self.lr = lr
        self.hidden_size = hidden_size
        self.shared: Any = None
        self.policy_head: Any = None
        self.value_head: Any = None
        self.optimizer: Any = None
        self.action_dim: int = 0

    def _build(self, obs_dim: int, action_dim: int):
        torch, nn = _t()
        self.action_dim = action_dim
        self.shared = nn.Sequential(nn.Linear(obs_dim, self.hidden_size), nn.ReLU())
        self.policy_head = nn.Sequential(nn.Linear(self.hidden_size, action_dim), nn.Softmax(dim=-1))
        self.value_head = nn.Linear(self.hidden_size, 1)
        params = list(self.shared.parameters()) + list(self.policy_head.parameters()) + list(self.value_head.parameters())
        self.optimizer = torch.optim.Adam(params, lr=self.lr)

    def act(self, obs):
        torch, _ = _t()
        if self.shared is None:
            return int(np.random.randint(max(self.action_dim, 1)))
        with torch.no_grad():
            features = self.shared(torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0))
            probs = self.policy_head(features)
            return int(torch.multinomial(probs, 1).item())

    def train(self, env, total_timesteps: int) -> dict[str, Any]:
        torch, _ = _t()
        obs, _ = env.reset()
        obs_dim = int(np.asarray(obs).flatten().shape[0])
        action_dim = int(getattr(env.action_space, "n", 1))
        self._build(obs_dim, action_dim)
        all_rewards: list[float] = []
        ep_reward = 0.0
        for step in range(total_timesteps):
            obs_t = torch.as_tensor(np.asarray(obs).flatten(), dtype=torch.float32).unsqueeze(0)
            features = self.shared(obs_t)
            probs = self.policy_head(features)
            value = self.value_head(features).squeeze()
            dist = torch.distributions.Categorical(probs)
            action = dist.sample()
            log_prob = dist.log_prob(action)
            obs_next, reward, terminated, truncated, _ = env.step(int(action.item()))
            done = terminated or truncated
            ep_reward += reward
            with torch.no_grad():
                next_t = torch.as_tensor(np.asarray(obs_next).flatten(), dtype=torch.float32).unsqueeze(0)
                next_value = self.value_head(self.shared(next_t)).squeeze()
                target = reward + self.gamma * next_value * (1 - float(done))
            advantage = target - value
            policy_loss = -(log_prob * advantage.detach()).mean()
            value_loss = advantage.pow(2).mean()
            loss = policy_loss + 0.5 * value_loss
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            obs = obs_next
            if done:
                all_rewards.append(ep_reward)
                ep_reward = 0.0
                obs, _ = env.reset()
        return {"episode_rewards": all_rewards, "n_episodes": len(all_rewards)}

    def save(self, path: str) -> None:
        torch, _ = _t()
        state = {
            "shared": self.shared.state_dict(),
            "policy": self.policy_head.state_dict(),
            "value": self.value_head.state_dict(),
        }
        torch.save(state, path)

    def load(self, path: str) -> None:
        torch, _ = _t()
        state = torch.load(path)
        self.shared.load_state_dict(state["shared"])
        self.policy_head.load_state_dict(state["policy"])
        self.value_head.load_state_dict(state["value"])


# ---------------------------------------------------------------------------
# Actor-Critic with Experience Replay
# ---------------------------------------------------------------------------


@register("ActorCriticExperienceReplayAgent", source="stock_prediction_models", category="rl_ac", kind="agent")
class ActorCriticExperienceReplayAgent(A3CAgent):
    """Off-policy actor-critic with replay buffer (ACER-lite)."""

    def __init__(self, replay_capacity: int = 10000, batch_size: int = 32, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.replay: deque = deque(maxlen=replay_capacity)
        self.batch_size = batch_size

    def train(self, env, total_timesteps: int) -> dict[str, Any]:
        torch, _ = _t()
        obs, _ = env.reset()
        obs_dim = int(np.asarray(obs).flatten().shape[0])
        action_dim = int(getattr(env.action_space, "n", 1))
        self._build(obs_dim, action_dim)
        all_rewards: list[float] = []
        ep_reward = 0.0
        for step in range(total_timesteps):
            obs_t = torch.as_tensor(np.asarray(obs).flatten(), dtype=torch.float32).unsqueeze(0)
            features = self.shared(obs_t)
            probs = self.policy_head(features)
            dist = torch.distributions.Categorical(probs)
            action = dist.sample()
            obs_next, reward, terminated, truncated, _ = env.step(int(action.item()))
            done = terminated or truncated
            self.replay.append((np.asarray(obs).flatten(), int(action.item()), float(reward), np.asarray(obs_next).flatten(), float(done)))
            obs = obs_next
            ep_reward += reward
            if done:
                all_rewards.append(ep_reward)
                ep_reward = 0.0
                obs, _ = env.reset()
            if len(self.replay) >= self.batch_size:
                batch = [self.replay[i] for i in np.random.choice(len(self.replay), self.batch_size, replace=False)]
                obs_b, act_b, rew_b, next_b, done_b = (np.array(x) for x in zip(*batch, strict=False))
                obs_t = torch.as_tensor(obs_b, dtype=torch.float32)
                next_t = torch.as_tensor(next_b, dtype=torch.float32)
                rew_t = torch.as_tensor(rew_b, dtype=torch.float32)
                done_t = torch.as_tensor(done_b, dtype=torch.float32)
                act_t = torch.as_tensor(act_b, dtype=torch.long)
                features_b = self.shared(obs_t)
                probs_b = self.policy_head(features_b)
                values_b = self.value_head(features_b).squeeze(-1)
                with torch.no_grad():
                    next_values = self.value_head(self.shared(next_t)).squeeze(-1)
                targets = rew_t + self.gamma * next_values * (1 - done_t)
                advantages = targets - values_b
                log_probs = torch.log(probs_b.gather(1, act_t.unsqueeze(-1)).squeeze(-1) + 1e-9)
                policy_loss = -(log_probs * advantages.detach()).mean()
                value_loss = advantages.pow(2).mean()
                loss = policy_loss + 0.5 * value_loss
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
        return {"episode_rewards": all_rewards, "n_episodes": len(all_rewards)}


__all__ = [
    "A3CAgent",
    "ActorCriticExperienceReplayAgent",
    "DoubleDuelingDQNAgent",
    "PolicyGradientAgent",
]
