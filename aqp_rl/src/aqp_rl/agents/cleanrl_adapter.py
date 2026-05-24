"""Thin adapter over `CleanRL <https://github.com/vwxyzjn/cleanrl>`_-style PPO.

CleanRL is single-file by design — we ship a minimal in-tree PPO loop
that mirrors `cleanrl/ppo_continuous_action.py`. Useful for transparent
debugging where every operation is in plain Python (vs SB3's heavier
abstraction).

Only continuous-action PPO is implemented here as a reference; researchers
can extend to SAC / DQN / DDPG by sub-classing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


def _import_torch():
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim

        return torch, nn, optim
    except ImportError as exc:  # pragma: no cover
        raise ImportError("CleanRLAdapter requires torch — install with `pip install torch`.") from exc


def _build_actor_critic(state_dim: int, action_dim: int, hidden: int = 64):
    torch, nn, _ = _import_torch()

    class _ActorCritic(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.shared = nn.Sequential(
                nn.Linear(state_dim, hidden),
                nn.Tanh(),
                nn.Linear(hidden, hidden),
                nn.Tanh(),
            )
            self.actor_mean = nn.Linear(hidden, action_dim)
            self.actor_log_std = nn.Parameter(torch.zeros(action_dim))
            self.critic = nn.Linear(hidden, 1)

        def forward(self, x):
            h = self.shared(x)
            mean = self.actor_mean(h)
            value = self.critic(h)
            return mean, value

        def get_action_and_value(self, x, action=None):
            mean, value = self.forward(x)
            std = torch.exp(self.actor_log_std)
            dist = torch.distributions.Normal(mean, std)
            if action is None:
                action = dist.sample()
            log_prob = dist.log_prob(action).sum(axis=-1)
            entropy = dist.entropy().sum(axis=-1)
            return action, log_prob, entropy, value

    return _ActorCritic()


class CleanRLAdapter(BaseRLAgent):
    """Reference single-file PPO implementation (continuous actions)."""

    rl_alias: ClassVar[str] = "CleanRLAdapter"
    rl_source: ClassVar[str] = "cleanrl"
    rl_category: ClassVar[str] = "drl"
    rl_tags: ClassVar[tuple[str, ...]] = ("cleanrl", "ppo", "single-file")

    algorithm: str = "PPO"

    def __init__(
        self,
        *,
        algorithm: str = "PPO",
        learning_rate: float = 3e-4,
        n_steps: int = 2048,
        update_epochs: int = 10,
        clip_coef: float = 0.2,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        hidden: int = 64,
        device: str = "cpu",
        **_: Any,
    ) -> None:
        if str(algorithm).upper() != "PPO":
            raise NotImplementedError(
                "CleanRLAdapter only ships PPO; extend the class for other algos."
            )
        self.algorithm = "PPO"
        self.learning_rate = float(learning_rate)
        self.n_steps = int(n_steps)
        self.update_epochs = int(update_epochs)
        self.clip_coef = float(clip_coef)
        self.gamma = float(gamma)
        self.gae_lambda = float(gae_lambda)
        self.hidden = int(hidden)
        self.device = str(device)
        self._env: gym.Env | None = None
        self._model: Any | None = None
        self._optimizer: Any | None = None

    def build(self, env: gym.Env) -> None:
        torch, _, optim = _import_torch()
        self._env = env
        state_dim = int(env.observation_space.shape[0])
        action_dim = int(env.action_space.shape[0]) if env.action_space.shape else int(env.action_space.n)
        self._model = _build_actor_critic(state_dim, action_dim, self.hidden).to(self.device)
        self._optimizer = optim.Adam(self._model.parameters(), lr=self.learning_rate, eps=1e-5)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        torch, nn, _ = _import_torch()
        if self._model is None or self._env is None or self._optimizer is None:
            raise RuntimeError("CleanRLAdapter not built. Call .build(env) first.")
        env = self._env
        steps_done = 0
        obs, _info = env.reset()
        while steps_done < int(total_timesteps):
            obs_buf, act_buf, logp_buf, rew_buf, val_buf, done_buf = [], [], [], [], [], []
            for _ in range(self.n_steps):
                with torch.no_grad():
                    obs_t = torch.as_tensor(np.asarray(obs, dtype=np.float32), device=self.device).unsqueeze(0)
                    action, log_prob, _entropy, value = self._model.get_action_and_value(obs_t)
                act_np = action.cpu().numpy()[0]
                next_obs, reward, terminated, truncated, _info = env.step(act_np)
                done = bool(terminated or truncated)
                obs_buf.append(np.asarray(obs, dtype=np.float32))
                act_buf.append(act_np)
                logp_buf.append(float(log_prob.item()))
                rew_buf.append(float(reward))
                val_buf.append(float(value.item()))
                done_buf.append(float(done))
                obs = next_obs if not done else env.reset()[0]
                steps_done += 1
                if steps_done >= int(total_timesteps):
                    break
            # GAE.
            with torch.no_grad():
                last_val = self._model.forward(torch.as_tensor(np.asarray(obs, dtype=np.float32), device=self.device).unsqueeze(0))[1].item()
            advantages = np.zeros(len(rew_buf), dtype=np.float32)
            last_gae = 0.0
            for t in reversed(range(len(rew_buf))):
                next_v = last_val if t == len(rew_buf) - 1 else val_buf[t + 1]
                next_done = done_buf[t]
                delta = rew_buf[t] + self.gamma * next_v * (1.0 - next_done) - val_buf[t]
                last_gae = delta + self.gamma * self.gae_lambda * (1.0 - next_done) * last_gae
                advantages[t] = last_gae
            returns = advantages + np.asarray(val_buf, dtype=np.float32)
            obs_t = torch.as_tensor(np.asarray(obs_buf, dtype=np.float32), device=self.device)
            act_t = torch.as_tensor(np.asarray(act_buf, dtype=np.float32), device=self.device)
            old_logp = torch.as_tensor(np.asarray(logp_buf, dtype=np.float32), device=self.device)
            adv_t = torch.as_tensor(advantages, device=self.device)
            ret_t = torch.as_tensor(returns, device=self.device)
            adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)
            for _ in range(self.update_epochs):
                _action, log_prob, entropy, value = self._model.get_action_and_value(obs_t, act_t)
                ratio = (log_prob - old_logp).exp()
                pg1 = ratio * adv_t
                pg2 = torch.clamp(ratio, 1.0 - self.clip_coef, 1.0 + self.clip_coef) * adv_t
                pg_loss = -torch.min(pg1, pg2).mean()
                v_loss = 0.5 * ((value.squeeze(-1) - ret_t) ** 2).mean()
                ent_loss = -entropy.mean()
                loss = pg_loss + 0.5 * v_loss + 0.01 * ent_loss
                self._optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self._model.parameters(), 0.5)
                self._optimizer.step()

    def save(self, path: str | Path) -> Path:
        if self._model is None:
            raise RuntimeError("CleanRLAdapter has nothing to save.")
        torch, _, _ = _import_torch()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        torch.save(self._model.state_dict(), str(p))
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        if env is not None and self._model is None:
            self.build(env)
        torch, _, _ = _import_torch()
        if self._model is None:
            raise RuntimeError("Build the adapter first.")
        self._model.load_state_dict(torch.load(str(path)))

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        torch, _, _ = _import_torch()
        if self._model is None:
            raise RuntimeError("Build the adapter first.")
        with torch.no_grad():
            obs_t = torch.as_tensor(np.asarray(obs, dtype=np.float32)).unsqueeze(0)
            mean, _ = self._model.forward(obs_t)
            if deterministic:
                action = mean.cpu().numpy()[0]
            else:
                std = torch.exp(self._model.actor_log_std)
                dist = torch.distributions.Normal(mean, std)
                action = dist.sample().cpu().numpy()[0]
        return action, None

    @property
    def model(self) -> Any:
        return self._model


__all__ = ["CleanRLAdapter"]
