"""Run a trained RL policy in evaluation mode and compute holdout metrics."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from aqp.backtest.metrics import summarise
from aqp.core.registry import build_from_config

logger = logging.getLogger(__name__)


def evaluate_policy(cfg: dict[str, Any], checkpoint: str) -> dict[str, Any]:
    """Roll out a trained SB3 policy on a held-out window and summarise."""
    env = build_from_config(cfg["env"])
    agent = build_from_config(cfg["agent"])
    agent.load(checkpoint, env=env)

    obs, _ = env.reset()
    done = False
    rewards: list[float] = []
    while not done:
        action, _ = agent.predict(obs, deterministic=True)
        obs, r, terminated, truncated, _ = env.step(action)
        rewards.append(float(r))
        done = bool(terminated or truncated)

    history = getattr(env, "history", None)
    if history is None or len(history) < 2:
        return {"error": "env has no history attribute", "reward_sum": float(np.sum(rewards))}

    import pandas as pd

    equity = pd.Series(history, name="equity")
    summary = summarise(equity)
    summary["reward_sum"] = float(np.sum(rewards))
    summary["n_steps"] = len(history)
    return summary
