"""Smoke + registration tests for Phase-4 paper-grade agent ports.

Verifies for each agent:

1. ``RLComponent`` metaclass registration with ``rl_kind='rl_agent'``
   and the expected ``rl_alias``.
2. Default constructor builds without error (no ``env`` needed).
3. The algorithm string + tags match the canonical paper provenance.

For SB3-backed agents we additionally check the underlying SB3
algorithm class loads. The ``InvestorImitatorAgent`` (custom PyTorch
REINFORCE) is smoke-tested end-to-end on a tiny CartPole episode to
verify the train/predict/save/load loop.
"""
from __future__ import annotations

from pathlib import Path

import gymnasium as gym
import pytest

from aqp_rl.agents.paper_grade import (
    DeepScalperAgent,
    DeepTraderAgent,
    EIIEAgent,
    ETEOAgent,
    HFTDDQNAgent,
    InvestorImitatorAgent,
    OPDAgent,
    PPOInhouseAgent,
)
from aqp_rl.core.base import RL_KIND_AGENT, list_rl_components


# --------------------------------------------------------------------------- registration


@pytest.mark.parametrize(
    "alias,cls",
    [
        ("eiie", EIIEAgent),
        ("deeptrader", DeepTraderAgent),
        ("investor_imitator", InvestorImitatorAgent),
        ("eteo", ETEOAgent),
        ("opd", OPDAgent),
        ("deepscalper", DeepScalperAgent),
        ("hft_ddqn", HFTDDQNAgent),
        ("ppo_inhouse", PPOInhouseAgent),
    ],
)
def test_paper_grade_agents_registered(alias: str, cls: type) -> None:
    registry = list_rl_components(RL_KIND_AGENT)
    assert alias in registry, f"alias {alias!r} not in registry {sorted(registry)}"
    assert registry[alias] is cls
    # All paper-grade agents declare ``trademaster`` or ``aqp`` provenance.
    assert cls.rl_source in {"trademaster", "aqp"}


def test_sb3_subclass_algorithm_strings():
    """SB3-backed paper-grade agents declare canonical algorithm strings."""
    assert EIIEAgent().algorithm == "DDPG"
    assert DeepTraderAgent().algorithm == "DDPG"
    assert ETEOAgent().algorithm == "PPO"
    assert DeepScalperAgent().algorithm == "DQN"
    assert HFTDDQNAgent().algorithm == "DQN"
    assert PPOInhouseAgent().algorithm == "PPO"


def test_ppo_inhouse_has_37_tricks_defaults():
    """PPOInhouse ships the Huang et al. ICLR 2022 defaults out of the box."""
    agent = PPOInhouseAgent()
    kwargs = agent.algo_kwargs
    assert kwargs["gae_lambda"] == pytest.approx(0.95)
    assert kwargs["clip_range"] == pytest.approx(0.2)
    assert kwargs["max_grad_norm"] == pytest.approx(0.5)
    assert kwargs["target_kl"] == pytest.approx(0.015)
    # value-clip mirrors clip_range by default.
    assert kwargs["clip_range_vf"] == pytest.approx(0.2)


def test_opd_composes_two_ppo_policies():
    """OPDAgent holds a teacher + student each wrapping SB3 PPO."""
    agent = OPDAgent()
    assert agent.teacher.algorithm == "PPO"
    assert agent.student.algorithm == "PPO"


# --------------------------------------------------------------------------- functional smoke


def test_investor_imitator_smoke_train(tmp_path: Path):
    """REINFORCE custom impl: build → train → predict → save → load on CartPole."""
    env = gym.make("CartPole-v1")
    try:
        agent = InvestorImitatorAgent(learning_rate=1e-3, hidden_dim=32, gamma=0.99)
        agent.build(env)
        # Tiny training pass — just enough to verify the loop runs.
        agent.train(total_timesteps=200)
        obs, _ = env.reset(seed=42)
        action, _ = agent.predict(obs, deterministic=True)
        assert isinstance(action, int)
        assert 0 <= action < env.action_space.n
        # Save + load round-trip.
        ckpt = tmp_path / "investor_imitator.pt"
        saved = agent.save(ckpt)
        assert saved.exists()
        agent2 = InvestorImitatorAgent(learning_rate=1e-3, hidden_dim=32)
        agent2.build(env)
        agent2.load(saved, env=env)
        action2, _ = agent2.predict(obs, deterministic=True)
        assert isinstance(action2, int)
    finally:
        env.close()


def test_investor_imitator_rejects_continuous_action_env():
    """REINFORCE expects Discrete — Box action space should raise."""
    env = gym.make("Pendulum-v1")
    try:
        agent = InvestorImitatorAgent()
        with pytest.raises(TypeError):
            agent.build(env)
    finally:
        env.close()


def test_sb3_subclass_build_smoke():
    """Each SB3-backed paper-grade agent builds on CartPole without error."""
    env = gym.make("CartPole-v1")
    try:
        # Continuous-action agents need a continuous action env; we use
        # Pendulum for those.
        pend = gym.make("Pendulum-v1")
        try:
            EIIEAgent().build(pend)
            DeepTraderAgent().build(pend)
            ETEOAgent().build(pend)
            PPOInhouseAgent().build(pend)
        finally:
            pend.close()
        # Discrete-action agents on CartPole.
        DeepScalperAgent().build(env)
        HFTDDQNAgent().build(env)
    finally:
        env.close()
