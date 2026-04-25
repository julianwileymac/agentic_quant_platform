"""RL training + introspection endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted, TrainRLRequest
from aqp.tasks.training_tasks import evaluate_rl, train_rl

router = APIRouter(prefix="/rl", tags=["rl"])


# ---------------------------------------------------------------------------
# Existing train / evaluate endpoints (unchanged).
# ---------------------------------------------------------------------------


@router.post("/train", response_model=TaskAccepted)
def start_training(req: TrainRLRequest) -> TaskAccepted:
    async_result = train_rl.delay(req.config, req.run_name)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/evaluate", response_model=TaskAccepted)
def start_evaluation(config: dict, checkpoint: str) -> TaskAccepted:
    async_result = evaluate_rl.delay(config, checkpoint)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


# ---------------------------------------------------------------------------
# Introspection endpoints — drive the RL UI dropdowns.
# ---------------------------------------------------------------------------


_APPLICATIONS: dict[str, dict[str, Any]] = {
    "stock_trading": {
        "label": "Single-stock trading",
        "module": "aqp.rl.applications.stock_trading",
        "entry": "train_stock_trading",
        "params": [
            {"name": "symbol", "type": "string", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo", "enum": ["ppo", "a2c", "ddpg", "td3", "sac", "dqn"]},
            {"name": "total_timesteps", "type": "integer", "default": 100000},
            {"name": "initial_balance", "type": "number", "default": 10000.0},
        ],
    },
    "portfolio_allocation": {
        "label": "Multi-asset portfolio allocation",
        "module": "aqp.rl.applications.portfolio_allocation",
        "entry": "train_portfolio_allocation",
        "params": [
            {"name": "symbols", "type": "array", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo", "enum": ["ppo", "a2c", "ddpg", "td3", "sac"]},
            {"name": "total_timesteps", "type": "integer", "default": 150000},
            {"name": "initial_balance", "type": "number", "default": 100000.0},
        ],
    },
    "cryptocurrency_trading": {
        "label": "Crypto trading",
        "module": "aqp.rl.applications.cryptocurrency_trading",
        "entry": "train_crypto_trading",
        "params": [
            {"name": "symbol", "type": "string", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo"},
            {"name": "total_timesteps", "type": "integer", "default": 100000},
        ],
    },
    "ensemble_strategy": {
        "label": "Ensemble (DRL + classical)",
        "module": "aqp.rl.applications.ensemble_strategy",
        "entry": "train_ensemble",
        "params": [],
    },
    "imitation_learning": {
        "label": "Imitation learning",
        "module": "aqp.rl.applications.imitation_learning",
        "entry": "train_imitation",
        "params": [],
    },
    "fundamental_portfolio_drl": {
        "label": "Fundamentals DRL + Markowitz overlay",
        "module": "aqp.rl.applications.fundamental_portfolio_drl",
        "entry": "train_fundamental_portfolio_drl",
        "params": [
            {"name": "symbols", "type": "array", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo"},
            {"name": "total_timesteps", "type": "integer", "default": 150000},
            {"name": "markowitz_blend", "type": "number", "default": 0.5},
            {"name": "markowitz_lookback", "type": "integer", "default": 252},
            {"name": "feature_set_name", "type": "string", "required": False},
        ],
    },
}


_ALGORITHMS: dict[str, dict[str, Any]] = {
    "sb3_ppo": {"label": "PPO (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "sb3_a2c": {"label": "A2C (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "sb3_ddpg": {"label": "DDPG (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "sb3_td3": {"label": "TD3 (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "sb3_sac": {"label": "SAC (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "sb3_dqn": {"label": "DQN (SB3)", "framework": "stable-baselines3", "policy": "MlpPolicy"},
    "in_house_q_learning": {"label": "Q-learning (in-house)", "framework": "in-house"},
    "in_house_double_q": {"label": "Double-Q (in-house)", "framework": "in-house"},
    "in_house_dueling_q": {"label": "Dueling-Q (in-house)", "framework": "in-house"},
    "in_house_recurrent_q": {"label": "Recurrent-Q (in-house)", "framework": "in-house"},
    "in_house_curiosity_q": {"label": "Curiosity-Q (in-house)", "framework": "in-house"},
    "in_house_actor_critic": {"label": "Actor-Critic (in-house)", "framework": "in-house"},
    "in_house_ac_duel": {"label": "Actor-Critic Dueling", "framework": "in-house"},
    "in_house_ac_recurrent": {"label": "Actor-Critic Recurrent", "framework": "in-house"},
    "in_house_es": {"label": "Evolution Strategy", "framework": "in-house"},
    "in_house_neat": {"label": "NEAT", "framework": "in-house"},
    "in_house_novelty": {"label": "Novelty search", "framework": "in-house"},
    "classical_turtle": {"label": "Turtle (classical)", "framework": "in-house"},
    "classical_moving_average": {"label": "Moving Average (classical)", "framework": "in-house"},
    "classical_abcd": {"label": "ABCD pattern (classical)", "framework": "in-house"},
    "classical_signal_rolling": {"label": "Signal rolling (classical)", "framework": "in-house"},
}


_ENVIRONMENTS: dict[str, dict[str, Any]] = {
    "stock_trading": {
        "label": "StockTradingEnv",
        "module": "aqp.rl.envs.stock_trading_env",
        "class": "StockTradingEnv",
        "action_space": "Continuous",
    },
    "stock_trading_discrete": {
        "label": "StockTradingDiscreteEnv",
        "module": "aqp.rl.envs.stock_trading_discrete",
        "class": "StockTradingDiscreteEnv",
        "action_space": "Discrete (3)",
    },
    "portfolio_allocation": {
        "label": "PortfolioAllocationEnv",
        "module": "aqp.rl.envs.portfolio_env",
        "class": "PortfolioAllocationEnv",
        "action_space": "Continuous (softmax weights)",
    },
}


@router.get("/envs")
def list_envs() -> dict[str, Any]:
    return {"envs": [{"key": k, **v} for k, v in _ENVIRONMENTS.items()]}


@router.get("/algos")
def list_algos() -> dict[str, Any]:
    return {"algos": [{"key": k, **v} for k, v in _ALGORITHMS.items()]}


@router.get("/applications")
def list_applications() -> dict[str, Any]:
    return {"applications": [{"key": k, **v} for k, v in _APPLICATIONS.items()]}


# ---------------------------------------------------------------------------
# One-shot application invocation.
# ---------------------------------------------------------------------------


class ApplicationRunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    run_name: str | None = None


@router.post("/applications/{name}/run", response_model=TaskAccepted)
def run_application(name: str, req: ApplicationRunRequest) -> TaskAccepted:
    """Fire a registered RL application as a Celery task."""
    spec = _APPLICATIONS.get(name)
    if spec is None:
        raise HTTPException(404, f"unknown RL application {name!r}")
    from aqp.tasks.training_tasks import run_rl_application

    async_result = run_rl_application.delay(name, dict(req.params or {}), req.run_name)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )
