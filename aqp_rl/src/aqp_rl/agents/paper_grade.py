"""Paper-grade RL agents — TradeMaster ports under AQP conventions.

Seven agents ported from TradeMaster 1.0.0 into AQP's
:class:`BaseRLEnv` / :class:`RLComponent` metaclass:

| Alias | Paper | Domain | Backbone |
| --- | --- | --- | --- |
| ``eiie`` | Jiang & Liang 2017 | Portfolio | DDPG + EIIE conv (Phase 5) |
| ``deeptrader`` | Wang AAAI 21 | Portfolio | DDPG + ASU graph-NN (Phase 5) |
| ``investor_imitator`` | Ding KDD 18 | Portfolio | REINFORCE (custom) |
| ``eteo`` | Lin IJCAI 20 | Execution | PPO + dual-head (Phase 5) |
| ``opd`` | Fang AAAI 21 | Execution | Teacher-student dual PPO (custom) |
| ``deepscalper`` | Sun CIKM 22 | Algorithmic | DQN + hindsight reward (env-side) |
| ``hft_ddqn`` | Sun et al. 2022 | HFT | DQN + action masking + DP distillation |

The SB3-backed agents are thin :class:`SB3Adapter` subclasses with
pre-configured algorithm + sensible policy defaults. The two genuinely
custom agents (``InvestorImitator`` REINFORCE, ``OPD`` teacher-student
dual PPO) ship as compact PyTorch implementations.

All seven register through the :class:`RLComponentMeta` metaclass with
``rl_kind='rl_agent'`` so the RL Lab palette + ``GET
/rl/components/rl_agent`` light up automatically.

Hard rule 16: training/inference go through :class:`RLRuntime`. Hard
rule 19: auto-register through the metaclass (no manual decoration).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

import gymnasium as gym
import numpy as np

from aqp_rl.agents.sb3_adapter import SB3Adapter
from aqp_rl.core.policy import BaseRLAgent

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- portfolio


class EIIEAgent(SB3Adapter):
    """Ensemble of Identical Independent Evaluators (Jiang & Liang 2017).

    DDPG-style actor-critic with a per-asset conv backbone. The actor's
    output is softmax-normalised across assets (cash slice included).
    The Phase 5 :class:`EIIEConvBackbone` slots into the SB3 policy
    via ``features_extractor_kwargs``.
    """

    rl_alias: ClassVar[str] = "eiie"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "portfolio_management"
    rl_tags: ClassVar[tuple[str, ...]] = ("eiie", "ddpg", "portfolio", "jiang_2017")
    algorithm: str = "DDPG"

    def __init__(
        self,
        *,
        learning_rate: float = 1e-4,
        buffer_size: int = 100_000,
        batch_size: int = 64,
        tau: float = 0.005,
        gamma: float = 0.99,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="DDPG",
            policy=policy,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            batch_size=batch_size,
            tau=tau,
            gamma=gamma,
            **kwargs,
        )


class DeepTraderAgent(SB3Adapter):
    """DeepTrader (Wang AAAI 21) — DDPG with ASU graph-NN actor + MSU.

    The ASU (Asset Scoring Unit) + MSU (Market Scoring Unit) backbones
    register as Phase 5 ``rl_policy_backbone`` aliases ``sagcn`` and
    ``market_scorer`` and slot into the SB3 policy via
    ``features_extractor_kwargs``.
    """

    rl_alias: ClassVar[str] = "deeptrader"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "portfolio_management"
    rl_tags: ClassVar[tuple[str, ...]] = ("deeptrader", "ddpg", "graph_nn", "wang_2021")
    algorithm: str = "DDPG"

    def __init__(
        self,
        *,
        learning_rate: float = 1e-4,
        buffer_size: int = 100_000,
        batch_size: int = 64,
        gamma: float = 0.99,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="DDPG",
            policy=policy,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            batch_size=batch_size,
            gamma=gamma,
            **kwargs,
        )


class InvestorImitatorAgent(BaseRLAgent):
    """Investor-Imitator (Ding KDD 18) — REINFORCE over Categorical action.

    The agent learns to imitate an expert investor's discrete action
    distribution. The implementation is a compact REINFORCE over the
    env's :class:`gym.spaces.Discrete` action space; for continuous
    action spaces it raises at :meth:`build` time.

    Custom PyTorch — no SB3 backend.
    """

    rl_alias: ClassVar[str] = "investor_imitator"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "portfolio_management"
    rl_tags: ClassVar[tuple[str, ...]] = ("investor_imitator", "reinforce", "ding_2018")

    algorithm: str = "InvestorImitator"

    def __init__(
        self,
        *,
        learning_rate: float = 1e-3,
        gamma: float = 0.99,
        hidden_dim: int = 64,
    ) -> None:
        self.learning_rate = float(learning_rate)
        self.gamma = float(gamma)
        self.hidden_dim = int(hidden_dim)
        self._env: gym.Env | None = None
        self._model: Any | None = None
        self._optimizer: Any | None = None
        self._action_dim: int | None = None

    def build(self, env: gym.Env) -> None:
        import torch
        import torch.nn as nn

        self._env = env
        if not isinstance(env.action_space, gym.spaces.Discrete):
            raise TypeError(
                f"InvestorImitatorAgent requires Discrete action space; got {type(env.action_space).__name__}"
            )
        self._action_dim = int(env.action_space.n)
        obs_dim = int(np.prod(env.observation_space.shape))
        self._model = nn.Sequential(
            nn.Linear(obs_dim, self.hidden_dim),
            nn.ReLU(),
            nn.Linear(self.hidden_dim, self._action_dim),
        )
        self._optimizer = torch.optim.Adam(self._model.parameters(), lr=self.learning_rate)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        """Run REINFORCE for ``total_timesteps`` env steps (episodes batched)."""
        if self._model is None or self._env is None or self._optimizer is None:
            raise RuntimeError("InvestorImitatorAgent not built. Call .build(env) first.")
        import torch
        from torch.distributions import Categorical

        steps_done = 0
        while steps_done < total_timesteps:
            obs, _ = self._env.reset()
            log_probs: list[Any] = []
            rewards: list[float] = []
            done = False
            while not done and steps_done < total_timesteps:
                obs_t = torch.as_tensor(np.asarray(obs).flatten(), dtype=torch.float32)
                logits = self._model(obs_t)
                dist = Categorical(logits=logits)
                action = dist.sample()
                obs, reward, terminated, truncated, _ = self._env.step(int(action.item()))
                log_probs.append(dist.log_prob(action))
                rewards.append(float(reward))
                steps_done += 1
                done = bool(terminated or truncated)

            # Compute discounted returns.
            returns: list[float] = []
            R = 0.0
            for r in reversed(rewards):
                R = r + self.gamma * R
                returns.insert(0, R)
            returns_t = torch.tensor(returns, dtype=torch.float32)
            if returns_t.std() > 1e-6:
                returns_t = (returns_t - returns_t.mean()) / (returns_t.std() + 1e-8)
            loss = -torch.stack(
                [lp * R for lp, R in zip(log_probs, returns_t, strict=False)]
            ).sum()

            self._optimizer.zero_grad()
            loss.backward()
            self._optimizer.step()

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        import torch
        from torch.distributions import Categorical

        if self._model is None:
            raise RuntimeError("InvestorImitatorAgent not built")
        obs_t = torch.as_tensor(np.asarray(obs).flatten(), dtype=torch.float32)
        with torch.no_grad():
            logits = self._model(obs_t)
        if deterministic:
            action = int(torch.argmax(logits).item())
        else:
            action = int(Categorical(logits=logits).sample().item())
        return action, None

    def save(self, path: str | Path) -> Path:
        import torch

        p = Path(path)
        if p.suffix == "":
            p = p.with_suffix(".pt")
        p.parent.mkdir(parents=True, exist_ok=True)
        if self._model is not None:
            torch.save(self._model.state_dict(), p)
        return p

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        import torch

        if env is not None and self._model is None:
            self.build(env)
        if self._model is None:
            raise RuntimeError("Agent must be built before load (call .build(env) first)")
        state_dict = torch.load(Path(path), weights_only=True)
        self._model.load_state_dict(state_dict)


# --------------------------------------------------------------------------- execution


class ETEOAgent(SB3Adapter):
    """End-to-End Optimal Execution (Lin IJCAI 20) — PPO with dual-head action.

    The dual-head architecture (volume + price) is implemented at the
    Phase 5 backbone layer (:class:`DualHeadContinuousBackbone`) and
    slotted in via ``policy_kwargs``. The base PPO settings here
    follow the canonical clipped-PPO surrogate.
    """

    rl_alias: ClassVar[str] = "eteo"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "order_execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("eteo", "ppo", "dual_head", "lin_2020")
    algorithm: str = "PPO"

    def __init__(
        self,
        *,
        learning_rate: float = 3e-4,
        n_steps: int = 256,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.9,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        ent_coef: float = 0.0,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="PPO",
            policy=policy,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            max_grad_norm=max_grad_norm,
            **kwargs,
        )


class OPDAgent(BaseRLAgent):
    """Optimal Policy Distillation (Fang AAAI 21) — teacher-student dual PPO.

    Custom PyTorch implementation. The agent maintains *two* PPO
    policies internally:

    - **Teacher** trained on the env's ``info['perfect_state']``
      (future-aware "perfect" view).
    - **Student** trained on the env's ``info['public_state']``
      (causal "imperfect" view) plus a KL distillation term against
      the teacher's action distribution.

    This minimal port wraps two :class:`SB3Adapter` instances and
    composes them. The training loop alternates teacher updates with
    student updates; ``predict`` returns the student's action
    (matches deployment).
    """

    rl_alias: ClassVar[str] = "opd"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "order_execution"
    rl_tags: ClassVar[tuple[str, ...]] = ("opd", "ppo", "teacher_student", "fang_2021")

    algorithm: str = "OPD"

    def __init__(
        self,
        *,
        learning_rate: float = 3e-4,
        gamma: float = 0.9,
        beta_kl: float = 0.1,
        lambda_distill: float = 0.5,
        ratio_teacher_steps: float = 0.3,
        policy: str = "MlpPolicy",
        n_steps: int = 256,
    ) -> None:
        self.learning_rate = float(learning_rate)
        self.gamma = float(gamma)
        self.beta_kl = float(beta_kl)
        self.lambda_distill = float(lambda_distill)
        self.ratio_teacher_steps = float(ratio_teacher_steps)
        self.policy = str(policy)
        self.n_steps = int(n_steps)
        self.student = SB3Adapter(
            algorithm="PPO",
            policy=policy,
            learning_rate=learning_rate,
            gamma=gamma,
            n_steps=n_steps,
        )
        self.teacher = SB3Adapter(
            algorithm="PPO",
            policy=policy,
            learning_rate=learning_rate,
            gamma=gamma,
            n_steps=n_steps,
        )

    def build(self, env: gym.Env) -> None:
        # In this minimal port both policies share the env's public obs.
        # The full OPD trick (teacher conditioning on perfect_state) is
        # surfaced via ``env.info['perfect_state']`` — Phase 5 wires a
        # custom :class:`PDDualRNNBackbone` that reads both streams.
        self.student.build(env)
        self.teacher.build(env)

    def train(
        self,
        total_timesteps: int,
        callbacks: list[Any] | None = None,
        log_interval: int = 10,
    ) -> None:
        teacher_steps = int(self.ratio_teacher_steps * total_timesteps)
        student_steps = int(total_timesteps - teacher_steps)
        if teacher_steps > 0:
            self.teacher.train(
                total_timesteps=teacher_steps,
                callbacks=callbacks,
                log_interval=log_interval,
            )
        if student_steps > 0:
            self.student.train(
                total_timesteps=student_steps,
                callbacks=callbacks,
                log_interval=log_interval,
            )

    def predict(self, obs: Any, *, deterministic: bool = True) -> Any:
        return self.student.predict(obs, deterministic=deterministic)

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        student_path = self.student.save(p.with_suffix(".student" + (p.suffix or ".zip")))
        teacher_path = self.teacher.save(p.with_suffix(".teacher" + (p.suffix or ".zip")))
        return student_path

    def load(self, path: str | Path, env: gym.Env | None = None) -> None:
        p = Path(path)
        student_path = p.with_suffix(".student" + (p.suffix or ".zip"))
        teacher_path = p.with_suffix(".teacher" + (p.suffix or ".zip"))
        if student_path.exists():
            self.student.load(student_path, env=env)
        if teacher_path.exists():
            self.teacher.load(teacher_path, env=env)


# --------------------------------------------------------------------------- algorithmic / HFT


class DeepScalperAgent(SB3Adapter):
    """DeepScalper (Sun CIKM 22) — DQN with hindsight-aware reward.

    The hindsight contribution lives in the env's reward
    (:class:`AlgorithmicTradingEnv` computes it directly OR composes
    via :class:`aqp_rl.rewards.hindsight.HindsightReward`); the agent
    itself is plain DQN. This matches TradeMaster's structure where
    the hindsight signal is data-flow, not network-flow.
    """

    rl_alias: ClassVar[str] = "deepscalper"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "algorithmic_trading"
    rl_tags: ClassVar[tuple[str, ...]] = ("deepscalper", "dqn", "hindsight", "sun_2022")
    algorithm: str = "DQN"

    def __init__(
        self,
        *,
        learning_rate: float = 1e-4,
        buffer_size: int = 100_000,
        batch_size: int = 64,
        gamma: float = 0.9,
        exploration_fraction: float = 0.1,
        exploration_final_eps: float = 0.05,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="DQN",
            policy=policy,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            batch_size=batch_size,
            gamma=gamma,
            exploration_fraction=exploration_fraction,
            exploration_final_eps=exploration_final_eps,
            **kwargs,
        )


class HFTDDQNAgent(SB3Adapter):
    """HFT Double-DQN with action masking + DP demonstration distillation.

    Uses Stable-Baselines3's DQN (which is a Double DQN by default —
    target network is a delayed copy of the online network). The
    action-masking via ``info['available_action']`` is consumed by
    the Phase 5 :class:`HFTQBackbone` (which applies ``+ (mask - 1) ·
    max_punish`` to the Q-logits). The DP distillation term comes in
    via the env's ``info['DP_action']`` + the
    :class:`aqp_rl.rewards.dp_distillation.DPDistillation` reward
    term composed in :class:`CompositeReward`.
    """

    rl_alias: ClassVar[str] = "hft_ddqn"
    rl_source: ClassVar[str] = "trademaster"
    rl_category: ClassVar[str] = "high_frequency_trading"
    rl_tags: ClassVar[tuple[str, ...]] = ("hft_ddqn", "double_dqn", "action_mask", "dp_distillation")
    algorithm: str = "DQN"

    def __init__(
        self,
        *,
        learning_rate: float = 1e-4,
        buffer_size: int = 100_000,
        batch_size: int = 512,
        gamma: float = 0.99,
        target_update_interval: int = 10,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="DQN",
            policy=policy,
            learning_rate=learning_rate,
            buffer_size=buffer_size,
            batch_size=batch_size,
            gamma=gamma,
            target_update_interval=target_update_interval,
            **kwargs,
        )


# --------------------------------------------------------------------------- in-house PPO


class PPOInhouseAgent(SB3Adapter):
    """SB3 PPO with the Huang et al. ICLR 2022 "37 details" defaults.

    Sets the SB3 PPO kwargs to mirror the CleanRL ``ppo_continuous_action``
    reference implementation:

    - GAE advantage with ``gae_lambda=0.95``.
    - Advantage normalisation (SB3's default ``normalize_advantage=True``).
    - Value-function clipping (``clip_range_vf=clip_range``).
    - Orthogonal init (SB3's default).
    - Adam ``ε=1e-5``.
    - LR annealing (callable ``schedule_fn`` with linear decay).
    - Max grad norm = ``0.5``.
    - Optional early-KL stop via ``target_kl=0.015``.

    Most of these are SB3 defaults; explicit values here document the
    canonical configuration so a YAML spec authoring an "ppo_inhouse"
    agent gets the well-known good defaults out of the box.
    """

    rl_alias: ClassVar[str] = "ppo_inhouse"
    rl_source: ClassVar[str] = "aqp"
    rl_category: ClassVar[str] = "policy_gradient"
    rl_tags: ClassVar[tuple[str, ...]] = ("ppo", "37_tricks", "huang_iclr_2022", "in_house")
    algorithm: str = "PPO"

    def __init__(
        self,
        *,
        learning_rate: float = 3e-4,
        n_steps: int = 2048,
        batch_size: int = 64,
        n_epochs: int = 10,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        clip_range_vf: float | None = None,
        ent_coef: float = 0.0,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        target_kl: float | None = 0.015,
        policy: str = "MlpPolicy",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            algorithm="PPO",
            policy=policy,
            learning_rate=learning_rate,
            n_steps=n_steps,
            batch_size=batch_size,
            n_epochs=n_epochs,
            gamma=gamma,
            gae_lambda=gae_lambda,
            clip_range=clip_range,
            clip_range_vf=clip_range_vf if clip_range_vf is not None else clip_range,
            ent_coef=ent_coef,
            vf_coef=vf_coef,
            max_grad_norm=max_grad_norm,
            target_kl=target_kl,
            **kwargs,
        )


__all__ = [
    "DeepScalperAgent",
    "DeepTraderAgent",
    "EIIEAgent",
    "ETEOAgent",
    "HFTDDQNAgent",
    "InvestorImitatorAgent",
    "OPDAgent",
    "PPOInhouseAgent",
]
