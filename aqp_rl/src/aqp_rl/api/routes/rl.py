"""RL training, evaluation, lab, and component-introspection routes.

Backwards-compat:
- ``POST /rl/train``, ``POST /rl/evaluate``, ``POST /rl/applications/{name}/run``
  preserved for the existing UI quick-train surface.
- ``GET /rl/envs``, ``GET /rl/algos``, ``GET /rl/applications`` preserved.

New (FinRL + FinRobot inspired refactor):
- ``GET /rl/components`` — kinds list with counts.
- ``GET /rl/components/{kind}`` — registered impls + JSON schemas.
- ``GET /rl/components/{kind}/{name}/schema`` — single schema.
- ``POST /rl/lab/preview-reward`` — composite-reward decomposition over
  a synthetic trajectory.
- ``POST /rl/lab/preview-observation`` — observation builder shape /
  feature-name preview.
- ``POST /rl/lab/preview-action`` — action transform preview.
- ``POST /rl/specs`` — persist :class:`RLExperimentSpec` (CRUD).
- ``GET /rl/specs`` / ``GET /rl/specs/{id}`` — list / fetch.
- ``GET /rl/specs/{id}/versions`` — version history.
- ``POST /rl/specs/{id}/run`` — fire :func:`train_rl_experiment` task.
- ``GET /rl/runs`` / ``GET /rl/runs/{id}`` — run ledger.
- ``GET /rl/runs/{id}/episodes`` / ``/equity`` / ``/trajectories`` /
  ``/reward-decomposition`` — DuckDB-view-backed payloads.
- ``POST /rl/runs/{id}/replay`` — re-roll on new window.
- ``POST /rl/data-pipelines/preview`` — data-pipeline preview.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from aqp.api.security import secure_router
from aqp.api.schemas import TaskAccepted, TrainRLRequest
from aqp_models.tasks.training_tasks import evaluate_rl, train_rl

logger = logging.getLogger(__name__)

router = secure_router(prefix="/rl", tags=["rl"], default_scope="data:read")


# ---------------------------------------------------------------------------
# Backwards-compat: existing train / evaluate / applications endpoints.
# ---------------------------------------------------------------------------


@router.post("/train", response_model=TaskAccepted)
def start_training(req: TrainRLRequest) -> TaskAccepted:
    async_result = train_rl.delay(req.config, req.run_name)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/evaluate", response_model=TaskAccepted)
def start_evaluation(config: dict, checkpoint: str) -> TaskAccepted:
    async_result = evaluate_rl.delay(config, checkpoint)
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


@router.post("/halt-all")
def halt_all_rl() -> dict[str, Any]:
    """Halt every running RL train / paper / evaluate / replay run.

    Idempotent kill-switch fan-out target. Selects every
    :class:`~aqp.persistence.models_rl.RLRun` with
    ``status in {pending, running}`` and a populated ``task_id`` and
    asks Celery to revoke + terminate the worker process. Each row
    is flipped to ``status="halted"`` so the lab UI updates without a
    polling delay.
    """
    from sqlalchemy import select as _select

    from aqp.persistence.db import get_session
    from aqp.persistence.models_rl import RLRun
    from aqp.tasks.celery_app import celery_app as _celery

    revoked: list[str] = []
    failed: list[dict[str, str]] = []
    with get_session() as s:
        rows = (
            s.execute(_select(RLRun).where(RLRun.status.in_(["pending", "running"])))
            .scalars()
            .all()
        )
        for row in rows:
            tid = (row.task_id or "").strip()
            if tid:
                try:
                    _celery.control.revoke(tid, terminate=True, signal="SIGTERM")
                    revoked.append(tid)
                except Exception as exc:  # noqa: BLE001
                    failed.append({"task_id": tid, "error": str(exc)})
            row.status = "halted"
    return {"stopped": len(revoked), "task_ids": revoked, "failures": failed}


_APPLICATIONS: dict[str, dict[str, Any]] = {
    "stock_trading": {
        "label": "Single-stock trading",
        "module": "aqp_rl.applications.stock_trading",
        "entry": "train_stock_trading",
        "params": [
            {"name": "symbol", "type": "string", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {
                "name": "algo",
                "type": "string",
                "default": "ppo",
                "enum": ["ppo", "a2c", "ddpg", "td3", "sac", "dqn"],
            },
            {"name": "total_timesteps", "type": "integer", "default": 100000},
            {"name": "initial_balance", "type": "number", "default": 10000.0},
        ],
    },
    "portfolio_allocation": {
        "label": "Multi-asset portfolio allocation",
        "module": "aqp_rl.applications.portfolio_allocation",
        "entry": "train_portfolio_allocation",
        "params": [
            {"name": "symbols", "type": "array", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo"},
            {"name": "total_timesteps", "type": "integer", "default": 150000},
            {"name": "initial_balance", "type": "number", "default": 100000.0},
        ],
    },
    "cryptocurrency_trading": {
        "label": "Crypto trading (FinRL multi-crypto env)",
        "module": "aqp_rl.applications.cryptocurrency_trading",
        "entry": "train_crypto_trading",
        "params": [
            {"name": "symbols", "type": "array", "required": True},
            {"name": "start", "type": "string", "required": True, "format": "date"},
            {"name": "end", "type": "string", "required": True, "format": "date"},
            {"name": "algo", "type": "string", "default": "ppo"},
            {"name": "total_timesteps", "type": "integer", "default": 100000},
        ],
    },
    "ensemble_strategy": {
        "label": "Ensemble (DRL + classical)",
        "module": "aqp_rl.applications.ensemble_strategy",
        "entry": "train_ensemble",
        "params": [],
    },
    "imitation_learning": {
        "label": "Imitation learning (BC / GAIL)",
        "module": "aqp_rl.applications.imitation_learning",
        "entry": "train_imitation",
        "params": [
            {"name": "method", "type": "string", "default": "bc", "enum": ["bc", "gail"]},
        ],
    },
    "fundamental_portfolio_drl": {
        "label": "Fundamentals DRL + Markowitz overlay",
        "module": "aqp_rl.applications.fundamental_portfolio_drl",
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
    "sb3_recurrent_ppo": {"label": "RecurrentPPO (sb3-contrib)", "framework": "sb3-contrib"},
    "sb3_trpo": {"label": "TRPO (sb3-contrib)", "framework": "sb3-contrib"},
    "sb3_qrdqn": {"label": "QR-DQN (sb3-contrib)", "framework": "sb3-contrib"},
    "sb3_maskable_ppo": {"label": "MaskablePPO (sb3-contrib)", "framework": "sb3-contrib"},
    "elegantrl_ppo": {"label": "PPO (ElegantRL)", "framework": "elegantrl"},
    "elegantrl_sac": {"label": "SAC (ElegantRL)", "framework": "elegantrl"},
    "rllib_ppo": {"label": "PPO (Ray RLlib)", "framework": "ray-rllib"},
    "rllib_dqn": {"label": "DQN (Ray RLlib)", "framework": "ray-rllib"},
    "cleanrl_ppo": {"label": "PPO (CleanRL reference)", "framework": "cleanrl"},
    "llm_hybrid": {"label": "LLM-hybrid (FinRobot bridge)", "framework": "aqp"},
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
        "label": "StockTradingEnv (continuous weights)",
        "module": "aqp_rl.envs.stock_trading_env",
        "class": "StockTradingEnv",
        "action_space": "Continuous",
    },
    "stock_trading_discrete": {
        "label": "StockTradingDiscreteEnv (single-stock)",
        "module": "aqp_rl.envs.stock_trading_discrete",
        "class": "StockTradingDiscreteEnv",
        "action_space": "Discrete (3)",
    },
    "portfolio_allocation": {
        "label": "PortfolioAllocationEnv (softmax)",
        "module": "aqp_rl.envs.portfolio_env",
        "class": "PortfolioAllocationEnv",
        "action_space": "Continuous (softmax weights)",
    },
    "finrl_stock_trading": {
        "label": "FinRLStockTradingEnv (share lots, hmax)",
        "module": "aqp_rl.envs.finrl_stock_env",
        "class": "FinRLStockTradingEnv",
        "action_space": "Continuous (integer shares)",
    },
    "finrl_stock_trading_np": {
        "label": "FinRLStockTradingNpEnv (numpy fast path)",
        "module": "aqp_rl.envs.finrl_stock_np_env",
        "class": "FinRLStockTradingNpEnv",
        "action_space": "Continuous",
    },
    "finrl_portfolio_cov": {
        "label": "FinRLPortfolioCovEnv (covariance + softmax)",
        "module": "aqp_rl.envs.finrl_portfolio_cov_env",
        "class": "FinRLPortfolioCovEnv",
        "action_space": "Continuous (softmax weights)",
    },
    "finrl_crypto": {
        "label": "FinRLCryptoEnv (lookback stack)",
        "module": "aqp_rl.envs.finrl_crypto_env",
        "class": "FinRLCryptoEnv",
        "action_space": "Continuous",
    },
    "options": {
        "label": "OptionsTradingEnv (placeholder)",
        "module": "aqp_rl.envs.options_env",
        "class": "OptionsTradingEnv",
        "action_space": "Continuous",
    },
    "execution": {
        "label": "ExecutionEnv (placeholder)",
        "module": "aqp_rl.envs.execution_env",
        "class": "ExecutionEnv",
        "action_space": "Continuous",
    },
    "market_making": {
        "label": "MarketMakingEnv (placeholder)",
        "module": "aqp_rl.envs.market_making_env",
        "class": "MarketMakingEnv",
        "action_space": "Continuous",
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


class ApplicationRunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    run_name: str | None = None


@router.post("/applications/{name}/run", response_model=TaskAccepted)
def run_application(name: str, req: ApplicationRunRequest) -> TaskAccepted:
    spec = _APPLICATIONS.get(name)
    if spec is None:
        raise HTTPException(404, f"unknown RL application {name!r}")
    from aqp_models.tasks.training_tasks import run_rl_application

    async_result = run_rl_application.delay(name, dict(req.params or {}), req.run_name)
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


# ---------------------------------------------------------------------------
# New: component / schema introspection.
# ---------------------------------------------------------------------------


@router.get("/components")
def list_components() -> dict[str, Any]:
    """Return ``{kind: count}`` for every registered RL component kind."""
    # Make sure every component module has been imported so the registry is populated.
    import aqp_rl  # noqa: F401  pylint: disable=unused-import

    from aqp_rl.core.schemas import list_kinds_with_counts

    return {"kinds": list_kinds_with_counts()}


@router.get("/components/{kind}")
def list_components_of_kind(kind: str) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp_rl.core.base import RL_KINDS
    from aqp_rl.core.schemas import list_component_schemas

    if kind not in RL_KINDS:
        raise HTTPException(404, f"unknown RL component kind {kind!r}")
    return {"kind": kind, "components": list_component_schemas(kind)}


@router.get("/components/{kind}/{name}/schema")
def component_schema_route(kind: str, name: str) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp_rl.core.base import RL_KINDS
    from aqp_rl.core.schemas import list_component_schemas

    if kind not in RL_KINDS:
        raise HTTPException(404, f"unknown RL component kind {kind!r}")
    schemas = list_component_schemas(kind)
    if name not in schemas:
        raise HTTPException(404, f"unknown {kind} component {name!r}")
    return schemas[name]


# ---------------------------------------------------------------------------
# Lab preview endpoints.
# ---------------------------------------------------------------------------


class RewardPreviewRequest(BaseModel):
    reward: dict[str, Any]
    trajectory: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/lab/preview-reward")
def preview_reward(req: RewardPreviewRequest) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp.core.registry import build_from_config
    from aqp_rl.core.reward import BaseRewardModel

    model = build_from_config(req.reward)
    if not isinstance(model, BaseRewardModel):
        raise HTTPException(400, "reward must build a BaseRewardModel subclass")
    out: list[dict[str, Any]] = []
    model.reset()
    for step in req.trajectory:
        prev = step.get("state", {})
        nxt = step.get("next_state", prev)
        action = step.get("action")
        info: dict[str, Any] = dict(step.get("info", {}))
        reward = float(model.compute(prev, action, nxt, info))
        out.append(
            {
                "step": step.get("step"),
                "reward": reward,
                "decomposition": dict(info.get("reward_terms", {})),
            }
        )
    return {"steps": out}


class ObservationPreviewRequest(BaseModel):
    observation: dict[str, Any]
    env_states: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/lab/preview-observation")
def preview_observation(req: ObservationPreviewRequest) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp.core.registry import build_from_config
    from aqp_rl.core.observation import BaseObservationBuilder

    builder = build_from_config(req.observation)
    if not isinstance(builder, BaseObservationBuilder):
        raise HTTPException(400, "observation must build a BaseObservationBuilder subclass")
    out = []
    for idx, state in enumerate(req.env_states):
        try:
            vec = builder.build(idx, state)
            out.append({"step": idx, "obs": vec.tolist()})
        except Exception as exc:  # noqa: BLE001
            out.append({"step": idx, "error": str(exc)})
    return {
        "feature_names": builder.feature_names(),
        "output_shape": list(builder.output_shape),
        "samples": out,
    }


class ActionPreviewRequest(BaseModel):
    action: dict[str, Any]
    raw_actions: list[Any] = Field(default_factory=list)


@router.post("/lab/preview-action")
def preview_action(req: ActionPreviewRequest) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp.core.registry import build_from_config
    from aqp_rl.core.action import BaseActionSpace

    space = build_from_config(req.action)
    if not isinstance(space, BaseActionSpace):
        raise HTTPException(400, "action must build a BaseActionSpace subclass")
    out = []
    for raw in req.raw_actions:
        try:
            transformed = space.transform(raw)
            try:
                value: Any = transformed.tolist()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                value = transformed
            out.append({"raw": raw, "transformed": value})
        except Exception as exc:  # noqa: BLE001
            out.append({"raw": raw, "error": str(exc)})
    return {
        "gym_space": str(space.gym_space()),
        "samples": out,
    }


# ---------------------------------------------------------------------------
# Specs CRUD + run.
# ---------------------------------------------------------------------------


class SpecCreateRequest(BaseModel):
    spec: dict[str, Any]


@router.post("/specs")
def create_spec(req: SpecCreateRequest) -> dict[str, Any]:
    from aqp_rl.registry import add_spec, persist_spec
    from aqp_rl.spec import RLExperimentSpec

    try:
        spec = RLExperimentSpec.model_validate(req.spec)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"invalid RLExperimentSpec: {exc}") from exc
    add_spec(spec)
    version_id = persist_spec(spec)
    return {"slug": spec.slug, "name": spec.name, "version_id": version_id}


@router.get("/specs")
def list_specs() -> dict[str, Any]:
    from aqp_rl.registry import list_rl_specs

    return {
        "specs": [
            {
                "slug": s.slug,
                "name": s.name,
                "kind": s.kind,
                "description": s.description,
            }
            for s in list_rl_specs()
        ]
    }


@router.get("/specs/{slug}")
def get_spec(slug: str) -> dict[str, Any]:
    from aqp_rl.registry import get_rl_spec

    try:
        spec = get_rl_spec(slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return spec.model_dump(mode="json")


@router.get("/specs/{slug}/versions")
def list_spec_versions(slug: str) -> dict[str, Any]:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import (
            RLExperimentSpec as RLSpecRow,
            RLExperimentVersion,
        )
    except Exception:
        return {"versions": []}
    out: list[dict[str, Any]] = []
    with SessionLocal() as session:
        spec_row = session.query(RLSpecRow).filter(RLSpecRow.slug == slug).one_or_none()
        if spec_row is None:
            return {"versions": []}
        rows = (
            session.query(RLExperimentVersion)
            .filter(RLExperimentVersion.spec_id == spec_row.id)
            .order_by(RLExperimentVersion.version.desc())
            .all()
        )
        for r in rows:
            out.append(
                {
                    "version_id": r.id,
                    "version": r.version,
                    "spec_hash": r.spec_hash,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    return {"versions": out}


class SpecRunRequest(BaseModel):
    target: str = "train"
    overrides: dict[str, Any] = Field(default_factory=dict)
    checkpoint: str | None = None
    new_window: dict[str, Any] | None = None


@router.post("/specs/{slug}/run", response_model=TaskAccepted)
def run_spec(slug: str, req: SpecRunRequest) -> TaskAccepted:
    from aqp_rl.registry import get_rl_spec

    try:
        spec = get_rl_spec(slug)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    if req.target == "train":
        from aqp_rl.tasks.rl_tasks import train_rl_experiment

        async_result = train_rl_experiment.delay(
            spec.model_dump(mode="json"),
            run_name=slug,
            overrides=req.overrides or None,
        )
    elif req.target == "evaluate":
        from aqp_rl.tasks.rl_tasks import evaluate_rl_experiment

        if not req.checkpoint:
            raise HTTPException(400, "checkpoint required for evaluate")
        async_result = evaluate_rl_experiment.delay(
            spec.model_dump(mode="json"),
            checkpoint=req.checkpoint,
            overrides=req.overrides or None,
        )
    elif req.target == "replay":
        from aqp_rl.tasks.rl_tasks import replay_trajectories

        if not req.checkpoint:
            raise HTTPException(400, "checkpoint required for replay")
        async_result = replay_trajectories.delay(
            spec.model_dump(mode="json"),
            checkpoint=req.checkpoint,
            new_window=req.new_window,
        )
    elif req.target == "walk_forward":
        from aqp_rl.tasks.rl_tasks import walk_forward_ensemble

        async_result = walk_forward_ensemble.delay(
            spec.model_dump(mode="json"),
            overrides=req.overrides or None,
        )
    elif req.target == "paper":
        from aqp_rl.tasks.rl_tasks import paper_trade_rl

        if not req.checkpoint:
            raise HTTPException(400, "checkpoint required for paper")
        async_result = paper_trade_rl.delay(
            spec.model_dump(mode="json"),
            checkpoint=req.checkpoint,
            overrides=req.overrides or None,
        )
    else:
        raise HTTPException(400, f"unknown target {req.target!r}")
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


# ---------------------------------------------------------------------------
# Runs ledger + episode / equity / trajectory queries.
# ---------------------------------------------------------------------------


@router.get("/runs")
def list_runs(
    status: str | None = None,
    target: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import RLRun
    except Exception:
        return {"runs": []}
    out: list[dict[str, Any]] = []
    with SessionLocal() as session:
        q = session.query(RLRun)
        if status:
            q = q.filter(RLRun.status == status)
        if target:
            q = q.filter(RLRun.target == target)
        rows = q.order_by(RLRun.started_at.desc()).limit(int(limit)).all()
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "spec_id": r.spec_id,
                    "version_id": r.version_id,
                    "target": r.target,
                    "status": r.status,
                    "task_id": r.task_id,
                    "mlflow_run_id": r.mlflow_run_id,
                    "checkpoint": r.checkpoint,
                    "mean_reward": r.mean_reward,
                    "sharpe": r.sharpe,
                    "max_drawdown": r.max_drawdown,
                    "final_value": r.final_value,
                    "total_return": r.total_return,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "ended_at": r.ended_at.isoformat() if r.ended_at else None,
                }
            )
    return {"runs": out}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import RLRun
    except Exception:
        raise HTTPException(503, "database unavailable")
    with SessionLocal() as session:
        r = session.query(RLRun).filter(RLRun.id == run_id).one_or_none()
        if r is None:
            raise HTTPException(404, f"unknown run {run_id!r}")
        return {
            "id": r.id,
            "spec_id": r.spec_id,
            "version_id": r.version_id,
            "target": r.target,
            "status": r.status,
            "task_id": r.task_id,
            "mlflow_run_id": r.mlflow_run_id,
            "checkpoint": r.checkpoint,
            "mean_reward": r.mean_reward,
            "total_reward": r.total_reward,
            "sharpe": r.sharpe,
            "max_drawdown": r.max_drawdown,
            "final_value": r.final_value,
            "total_return": r.total_return,
            "result_summary": r.result_summary or {},
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        }


@router.get("/runs/{run_id}/episodes")
def get_run_episodes(run_id: str) -> dict[str, Any]:
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models import RLEpisode
    except Exception:
        return {"episodes": []}
    out: list[dict[str, Any]] = []
    with SessionLocal() as session:
        rows = (
            session.query(RLEpisode)
            .filter(RLEpisode.run_id == run_id)
            .order_by(RLEpisode.episode.asc())
            .all()
        )
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "episode": r.episode,
                    "mean_reward": r.mean_reward,
                    "portfolio_value": r.portfolio_value,
                    "length": r.length,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
    return {"episodes": out}


def _query_iceberg_view(view_kind: str, run_id: str, episode: int | None) -> list[dict[str, Any]]:
    try:
        import duckdb

        from aqp_rl.trajectories.duckdb_views import ensure_duckdb_views
    except Exception:
        return []
    conn = duckdb.connect(":memory:")
    views = ensure_duckdb_views(conn)
    if view_kind not in views:
        return []
    where = "WHERE run_id = $run_id"
    params: dict[str, Any] = {"run_id": run_id}
    if episode is not None:
        where += " AND episode = $episode"
        params["episode"] = int(episode)
    sql = f"SELECT * FROM {views[view_kind]} {where} ORDER BY episode, step"
    try:
        df = conn.execute(sql, params).fetch_df()
        return df.to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001
        logger.debug("duckdb query failed for %s: %s", view_kind, exc)
        return []


@router.get("/runs/{run_id}/equity")
def get_run_equity(run_id: str, episode: int | None = None) -> dict[str, Any]:
    return {"rows": _query_iceberg_view("equity_curves", run_id, episode)}


@router.get("/runs/{run_id}/trajectories")
def get_run_trajectories(run_id: str, episode: int | None = None) -> dict[str, Any]:
    return {"rows": _query_iceberg_view("trajectories", run_id, episode)}


@router.get("/runs/{run_id}/reward-decomposition")
def get_run_reward_decomposition(run_id: str, episode: int | None = None) -> dict[str, Any]:
    return {"rows": _query_iceberg_view("reward_decomposition", run_id, episode)}


@router.get("/runs/{run_id}/actions")
def get_run_actions(run_id: str, episode: int | None = None) -> dict[str, Any]:
    return {"rows": _query_iceberg_view("action_logs", run_id, episode)}


class ReplayRequest(BaseModel):
    checkpoint: str
    new_window: dict[str, Any] = Field(default_factory=dict)


@router.post("/runs/{run_id}/replay", response_model=TaskAccepted)
def replay_run(run_id: str, req: ReplayRequest) -> TaskAccepted:
    """Re-roll a recorded run's policy on a different window."""
    try:
        from aqp.persistence.db import SessionLocal
        from aqp.persistence.models_rl import RLRun
    except Exception:
        raise HTTPException(503, "database unavailable")
    with SessionLocal() as session:
        run_row = session.query(RLRun).filter(RLRun.id == run_id).one_or_none()
        if run_row is None:
            raise HTTPException(404, f"unknown run {run_id!r}")
        version_id = run_row.version_id
    if version_id is None:
        raise HTTPException(400, f"run {run_id!r} has no spec version to replay")
    from aqp_rl.registry import replay_spec_version
    from aqp_rl.tasks.rl_tasks import replay_trajectories

    spec = replay_spec_version(version_id)
    async_result = replay_trajectories.delay(
        spec.model_dump(mode="json"),
        checkpoint=req.checkpoint,
        new_window=req.new_window or {},
    )
    return TaskAccepted(task_id=async_result.id, stream_url=f"/chat/stream/{async_result.id}")


# ---------------------------------------------------------------------------
# Data pipeline preview.
# ---------------------------------------------------------------------------


class DataPipelinePreviewRequest(BaseModel):
    pipeline: dict[str, Any]
    ticker_list: list[str] = Field(default_factory=list)
    start: str
    end: str
    time_interval: str = "1D"
    indicators: list[str] = Field(default_factory=list)
    use_vix: bool = False
    use_turbulence: bool = True
    head: int = Field(default=20, ge=1, le=500)


@router.post("/data-pipelines/preview")
def preview_data_pipeline(req: DataPipelinePreviewRequest) -> dict[str, Any]:
    import aqp_rl  # noqa: F401

    from aqp.core.registry import build_from_config
    from aqp_rl.core.data import BaseDataPipeline

    pipeline = build_from_config(req.pipeline)
    if not isinstance(pipeline, BaseDataPipeline):
        raise HTTPException(400, "pipeline must build a BaseDataPipeline subclass")
    try:
        bundle = pipeline.run_full(
            ticker_list=req.ticker_list,
            start=req.start,
            end=req.end,
            tech_indicator_list=req.indicators,
            time_interval=req.time_interval,
            use_vix=req.use_vix,
            use_turbulence=req.use_turbulence,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"pipeline run_full failed: {exc}") from exc
    head = bundle.df.head(int(req.head)).to_dict(orient="records") if bundle.df is not None else []
    return {
        "df_head": head,
        "row_count": int(len(bundle.df)) if bundle.df is not None else 0,
        "tickers": bundle.tickers,
        "indicators": bundle.indicators,
        "use_vix": bundle.use_vix,
        "use_turbulence": bundle.use_turbulence,
        "price_array_shape": list(bundle.price_array.shape),
        "tech_array_shape": list(bundle.tech_array.shape),
        "risk_array_shape": list(bundle.risk_array.shape) if bundle.risk_array is not None else [],
    }
