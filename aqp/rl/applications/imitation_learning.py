"""Imitation learning façade.

Wraps the community ``imitation`` library (BC / GAIL) for users who
want to seed a policy from expert demonstrations. Requires the
``[finrl-apps]`` optional group.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def train_behavior_cloning(
    env,
    trajectories: list[Any],
    *,
    total_timesteps: int = 20_000,
) -> dict[str, Any]:
    """Train Behavior Cloning on the supplied trajectories."""
    try:
        from imitation.algorithms.bc import BC
        from imitation.data.types import Trajectory
    except ImportError as exc:
        raise RuntimeError(
            "Install the `[finrl-apps]` extras to enable imitation learning "
            "(requires the `imitation` package)."
        ) from exc

    if not trajectories:
        raise ValueError("At least one trajectory is required.")

    bc = BC(
        observation_space=env.observation_space,
        action_space=env.action_space,
        demonstrations=trajectories,
    )
    bc.train(n_epochs=max(1, total_timesteps // max(1, len(trajectories))))
    return {"policy": bc.policy}


def train_gail(
    env,
    trajectories: list[Any],
    *,
    total_timesteps: int = 50_000,
) -> dict[str, Any]:
    """Train GAIL on the supplied trajectories."""
    try:
        from imitation.algorithms.adversarial.gail import GAIL
        from imitation.rewards.reward_nets import BasicRewardNet
        from stable_baselines3 import PPO
    except ImportError as exc:
        raise RuntimeError(
            "Install the `[finrl-apps]` extras to enable imitation learning."
        ) from exc

    reward_net = BasicRewardNet(env.observation_space, env.action_space)
    learner = PPO("MlpPolicy", env, verbose=0)
    trainer = GAIL(
        demonstrations=trajectories,
        demo_batch_size=32,
        venv=env,
        gen_algo=learner,
        reward_net=reward_net,
    )
    trainer.train(total_timesteps)
    return {"policy": learner.policy}
