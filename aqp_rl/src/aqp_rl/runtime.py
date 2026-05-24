"""``RLRuntime`` — execute an :class:`RLExperimentSpec` end-to-end with telemetry.

Mirrors :class:`aqp.bots.runtime.BotRuntime` and
:class:`aqp.agents.runtime.AgentRuntime`:

1. Snapshot + persist the spec version (hash-locked → ``rl_experiment_versions``).
2. Open an ``rl_runs`` row so the UI can correlate progress updates.
3. Drive the underlying execution by reusing existing primitives
   (``agent.train``, ``agent.predict``, ``BaseExperiment.run``).
4. Emit progress through :mod:`aqp.tasks._progress` so
   ``/chat/stream/<task_id>`` WebSocket consumers light up unchanged.
5. Persist trajectories / equity curves / action logs / reward terms
   via :class:`BaseTrajectoryStore` (Iceberg by default).
6. Finalise the run row with status + ``result_summary``.

Hard rule: this is the single sanctioned path for RL train / evaluate /
paper. Celery tasks (in :mod:`aqp.tasks.rl_tasks`) and the API routes
(in :mod:`aqp.api.routes.rl`) wrap :class:`RLRuntime` — they never call
``agent.train`` directly.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from aqp.config import settings
from aqp.core.registry import build_from_config
from aqp_rl.core.replay import BaseTrajectoryStore, InMemoryTrajectoryStore
from aqp_rl.spec import RLExperimentSpec
from aqp.tasks._progress import emit, emit_done, emit_error

logger = logging.getLogger(__name__)


@dataclass
class RLRunResult:
    """Outcome of any :class:`RLRuntime` action."""

    run_id: str
    spec_id: str | None
    version_id: str | None
    target: str  # train | evaluate | paper | replay | walk_forward
    status: str  # running | completed | error | cancelled
    started_at: float
    duration_ms: float = 0.0
    task_id: str | None = None
    mlflow_run_id: str | None = None
    checkpoint: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RLRuntime:
    """Executor for a single :class:`RLExperimentSpec`."""

    def __init__(
        self,
        spec: RLExperimentSpec,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        context: Any | None = None,
        trajectory_store: BaseTrajectoryStore | None = None,
        persist_trajectories: bool | None = None,
    ) -> None:
        self.spec = spec
        self.run_id = run_id or str(uuid.uuid4())
        self.task_id = task_id
        if context is None:
            try:
                from aqp.auth.context import default_context

                context = default_context()
            except Exception:
                context = None
        self.context = context
        self.persist_trajectories = (
            bool(persist_trajectories)
            if persist_trajectories is not None
            else bool(getattr(settings, "rl_persist_trajectories", True))
        )
        self.trajectory_store: BaseTrajectoryStore | None = trajectory_store
        self._spec_id: str | None = None
        self._version_id: str | None = None
        self._db_run_id: str | None = None
        self._data_pipeline: Any | None = None

    # ----------------------------------------------------------- public API

    def train(
        self,
        *,
        run_name: str | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> RLRunResult:
        """Run the training loop end-to-end and persist a run row."""
        return self._with_run(
            target="train",
            stage_message=f"Training RL spec {self.spec.name!r}",
            action=lambda: self._do_train(run_name=run_name, overrides=overrides or {}),
        )

    def evaluate(
        self,
        *,
        checkpoint: str,
        overrides: dict[str, Any] | None = None,
    ) -> RLRunResult:
        return self._with_run(
            target="evaluate",
            stage_message=f"Evaluating RL spec {self.spec.name!r}",
            action=lambda: self._do_evaluate(checkpoint=checkpoint, overrides=overrides or {}),
        )

    def paper(
        self,
        *,
        checkpoint: str,
        overrides: dict[str, Any] | None = None,
    ) -> RLRunResult:
        return self._with_run(
            target="paper",
            stage_message=f"Paper-trading RL spec {self.spec.name!r}",
            action=lambda: self._do_paper(checkpoint=checkpoint, overrides=overrides or {}),
        )

    def replay(
        self,
        *,
        checkpoint: str,
        new_window: dict[str, Any] | None = None,
    ) -> RLRunResult:
        return self._with_run(
            target="replay",
            stage_message=f"Replaying RL spec {self.spec.name!r}",
            action=lambda: self._do_replay(checkpoint=checkpoint, new_window=new_window or {}),
        )

    def walk_forward(
        self,
        *,
        overrides: dict[str, Any] | None = None,
    ) -> RLRunResult:
        return self._with_run(
            target="walk_forward",
            stage_message=f"Walk-forward ensemble for {self.spec.name!r}",
            action=lambda: self._do_walk_forward(overrides=overrides or {}),
        )

    # ----------------------------------------------------------- core actions

    def _do_train(
        self,
        *,
        run_name: str | None,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        env, agent = self._build_env_agent(overrides)
        self._open_trajectory_store()
        try:
            mlflow_run_id, checkpoint_path = self._train_with_mlflow(
                env=env,
                agent=agent,
                run_name=run_name,
            )
        finally:
            self._close_trajectory_store()
        # Run a quick eval pass on training window so metrics row gets populated.
        metrics = self._evaluate_inline(env=env, agent=agent)
        return {
            "mlflow_run_id": mlflow_run_id,
            "checkpoint": str(checkpoint_path) if checkpoint_path else None,
            "metrics": metrics,
            "spec_hash": self.spec.snapshot_hash(),
        }

    def _do_evaluate(
        self,
        *,
        checkpoint: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        env, agent = self._build_env_agent(overrides, prefer_evaluation_window=True)
        agent.load(checkpoint, env=env)
        metrics = self._rollout(env=env, agent=agent, episodes=self.spec.evaluation.episodes or 1)
        return {"checkpoint": str(checkpoint), "metrics": metrics}

    def _do_paper(
        self,
        *,
        checkpoint: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        env, agent = self._build_env_agent(overrides)
        agent.load(checkpoint, env=env)
        # Concrete papertrading env / Alpaca bridge handles real-time loop;
        # here we just rollout one "episode" against the live env.
        metrics = self._rollout(env=env, agent=agent, episodes=1)
        return {"checkpoint": str(checkpoint), "metrics": metrics, "mode": "paper"}

    def _do_replay(
        self,
        *,
        checkpoint: str,
        new_window: dict[str, Any],
    ) -> dict[str, Any]:
        # Override env start/end if a new window was passed.
        overrides = {"env": dict(new_window)} if new_window else {}
        env, agent = self._build_env_agent(overrides)
        agent.load(checkpoint, env=env)
        metrics = self._rollout(env=env, agent=agent, episodes=1)
        return {"checkpoint": str(checkpoint), "metrics": metrics, "window": new_window}

    def _do_walk_forward(self, *, overrides: dict[str, Any]) -> dict[str, Any]:
        if self.spec.ensembler is None:
            raise ValueError("walk_forward requires spec.ensembler to be set")
        ens_spec = self.spec.ensembler.spec or {}
        ensembler = build_from_config(ens_spec)
        return ensembler.train(self.spec, self)  # type: ignore[arg-type]

    # ----------------------------------------------------------- shared helpers

    def _build_env_agent(
        self,
        overrides: dict[str, Any],
        *,
        prefer_evaluation_window: bool = False,
    ) -> tuple[Any, Any]:
        env_cfg = self._merge(self.spec.env, overrides.get("env"))
        if env_cfg is None:
            raise ValueError("RLExperimentSpec.env must be set")
        if prefer_evaluation_window and self.spec.evaluation:
            kwargs = dict(env_cfg.get("kwargs", {}) or {})
            if self.spec.evaluation.start:
                kwargs["start"] = self.spec.evaluation.start
            if self.spec.evaluation.end:
                kwargs["end"] = self.spec.evaluation.end
            env_cfg = {**env_cfg, "kwargs": kwargs}

        # Spec.data_pipeline is the FinRL ``DataProcessor`` analogue.
        # Resolve it once here so the env can pull a fully-featurised
        # ``DataPipelineResult`` instead of hand-rolling its own
        # download/clean/indicators chain.
        data_pipeline = self._build_data_pipeline(overrides.get("data_pipeline"))
        self._data_pipeline = data_pipeline
        if data_pipeline is not None:
            env_kwargs = dict(env_cfg.get("kwargs", {}) or {})
            env_kwargs.setdefault("data_pipeline", data_pipeline)
            env_cfg = {**env_cfg, "kwargs": env_kwargs}

        env = build_from_config(env_cfg)

        self._maybe_install_stop_properly_wrapper(env)

        agent_cfg = self._merge(self.spec.agent, overrides.get("agent"))
        if agent_cfg is None:
            raise ValueError("RLExperimentSpec.agent must be set")
        agent = build_from_config(agent_cfg)
        agent.build(env)
        return env, agent

    def _maybe_install_stop_properly_wrapper(self, env: Any) -> None:
        """Install :class:`StopProperlyWrapper` when the spec opts in.

        Honours the canonical ``coef in [0, 1]`` semantics: ``0`` =
        draconian zero-reward for truncated steps; ``1`` = no penalty
        (wrapper still installed so telemetry hooks fire).
        """
        coef = getattr(self.spec.training, "stop_properly_penalty_coef", None)
        if coef is None:
            return
        try:
            from aqp_rl.rewards.stop_properly import StopProperlyWrapper
        except Exception:
            logger.debug("StopProperlyWrapper unavailable; skipping wrap", exc_info=True)
            return
        inner = getattr(env, "reward_model", None)
        if inner is None:
            logger.warning(
                "stop_properly_penalty_coef=%s requested but env has no reward_model -- skipping wrap",
                coef,
            )
            return
        env.reward_model = StopProperlyWrapper(inner=inner, coef=float(coef))

    def _build_data_pipeline(self, override: Any | None) -> Any | None:
        """Resolve ``spec.data_pipeline`` into a :class:`BaseDataPipeline`.

        Returns ``None`` when no pipeline is configured. Envs that
        manage their own data (synthetic envs, replay envs that read
        ``rl.trajectories`` directly) stay unaffected because the env
        kwarg is only injected when a pipeline resolves.
        """
        pipeline_ref = override if override is not None else self.spec.data_pipeline
        if pipeline_ref is None:
            return None
        spec_dict: dict[str, Any] | None = None
        if hasattr(pipeline_ref, "spec") and getattr(pipeline_ref, "spec", None):
            spec_dict = dict(getattr(pipeline_ref, "spec"))
        elif isinstance(pipeline_ref, dict) and "spec" in pipeline_ref and pipeline_ref["spec"]:
            spec_dict = dict(pipeline_ref["spec"])
        elif isinstance(pipeline_ref, dict) and "class" in pipeline_ref:
            spec_dict = dict(pipeline_ref)
        if spec_dict is None:
            return None
        try:
            return build_from_config(spec_dict)
        except Exception:
            logger.exception("data_pipeline construction failed; env will fall back to defaults")
            return None

    @staticmethod
    def _merge(base: dict[str, Any] | None, over: dict[str, Any] | None) -> dict[str, Any] | None:
        if base is None and over is None:
            return None
        out = dict(base or {})
        if over:
            kwargs = {**(out.get("kwargs") or {}), **(over.get("kwargs") or {})}
            out = {**out, **{k: v for k, v in over.items() if k != "kwargs"}, "kwargs": kwargs}
        return out

    def _train_with_mlflow(
        self,
        *,
        env: Any,
        agent: Any,
        run_name: str | None,
    ) -> tuple[str | None, Path | None]:
        try:
            import mlflow
            import mlflow.pytorch
        except Exception:  # pragma: no cover
            logger.warning("mlflow unavailable — running training without tracking")
            agent.train(
                total_timesteps=int(self.spec.training.total_timesteps),
                log_interval=int(self.spec.training.log_interval),
            )
            ckpt = self._save_checkpoint(agent, run_name=run_name or self.spec.slug)
            return None, ckpt

        experiment = (
            self.spec.mlflow.experiment
            or getattr(settings, "mlflow_experiment", None)
            or "aqp-rl"
        )
        mlflow.set_tracking_uri(getattr(settings, "mlflow_tracking_uri", "http://localhost:5000"))
        mlflow.set_experiment(experiment)
        run_name_resolved = (
            run_name or f"{getattr(agent, 'algorithm', 'rl').lower()}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        )
        with mlflow.start_run(run_name=run_name_resolved) as run:
            agent_kwargs = (self.spec.agent or {}).get("kwargs", {}) or {}
            mlflow.log_params({f"agent.{k}": str(v) for k, v in agent_kwargs.items()})
            mlflow.log_params({"training.total_timesteps": self.spec.training.total_timesteps})
            try:
                mlflow.pytorch.autolog()
            except Exception:  # pragma: no cover
                logger.debug("mlflow.pytorch.autolog unavailable", exc_info=True)
            agent.train(
                total_timesteps=int(self.spec.training.total_timesteps),
                log_interval=int(self.spec.training.log_interval),
            )
            ckpt = self._save_checkpoint(agent, run_name=run_name_resolved)
            try:
                if ckpt is not None:
                    mlflow.log_artifact(str(ckpt))
            except Exception:  # noqa: BLE001
                logger.debug("mlflow log_artifact failed", exc_info=True)
            if self.spec.mlflow.register_model_as:
                try:
                    mlflow.register_model(
                        f"runs:/{run.info.run_id}/policy",
                        self.spec.mlflow.register_model_as,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("mlflow register_model failed", exc_info=True)
            return run.info.run_id, ckpt

    def _save_checkpoint(self, agent: Any, *, run_name: str) -> Path | None:
        try:
            base = Path(getattr(settings, "models_dir", "./data/models")) / "rl" / run_name
            base.mkdir(parents=True, exist_ok=True)
            ckpt = base / "policy.zip"
            agent.save(ckpt)
            return ckpt
        except Exception:  # noqa: BLE001
            logger.exception("checkpoint save failed for %s", run_name)
            return None

    def _evaluate_inline(self, *, env: Any, agent: Any) -> dict[str, Any]:
        try:
            return self._rollout(env=env, agent=agent, episodes=1)
        except Exception:  # noqa: BLE001
            logger.debug("inline eval rollout failed", exc_info=True)
            return {}

    def _rollout(self, *, env: Any, agent: Any, episodes: int) -> dict[str, Any]:
        all_metrics: list[dict[str, Any]] = []
        for ep in range(int(episodes)):
            obs, _ = env.reset()
            done = False
            rewards: list[float] = []
            step_idx = 0
            while not done:
                action, _ = agent.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                rewards.append(float(reward))
                self._record_step(
                    episode=ep,
                    step=step_idx,
                    info=info,
                    action=action,
                    reward=float(reward),
                )
                step_idx += 1
                done = bool(terminated or truncated)
            history = list(getattr(env, "history", []) or [])
            metrics = _summarise_history(rewards, history)
            self._record_episode(episode=ep, metrics=metrics)
            all_metrics.append(metrics)
        if not all_metrics:
            return {}
        avg = {
            k: float(sum(m.get(k, 0.0) for m in all_metrics) / len(all_metrics))
            for k in all_metrics[0]
        }
        avg["episodes"] = len(all_metrics)
        return avg

    # ----------------------------------------------------------- DB plumbing

    def _snapshot_spec(self) -> tuple[str | None, str | None]:
        from aqp_rl.registry import persist_spec

        version_id = persist_spec(self.spec)
        spec_id = self._lookup_spec_id()
        self._spec_id = spec_id
        self._version_id = version_id
        return spec_id, version_id

    def _lookup_spec_id(self) -> str | None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rl import RLExperimentSpec as RLSpecRow

            with SessionLocal() as session:
                row = (
                    session.query(RLSpecRow)
                    .filter(RLSpecRow.slug == self.spec.slug)
                    .one_or_none()
                )
                return row.id if row is not None else None
        except Exception:  # pragma: no cover
            return None

    def _open_run_row(self, *, target: str, version_id: str | None) -> str | None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rl import RLRun

            with SessionLocal() as session:
                row = RLRun(
                    id=str(uuid.uuid4()),
                    spec_id=self._spec_id,
                    version_id=version_id,
                    target=target,
                    task_id=self.task_id,
                    status="running",
                    started_at=datetime.utcnow(),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.flush()
                return row.id
        except Exception:  # pragma: no cover
            logger.debug("Could not open rl_runs row", exc_info=True)
            return None

    def _finalise_run_row(
        self,
        run_db_id: str | None,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: str | None,
        mlflow_run_id: str | None,
        checkpoint: str | None,
    ) -> None:
        if run_db_id is None:
            return
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models_rl import RLRun

            with SessionLocal() as session:
                row = session.get(RLRun, run_db_id)
                if row is None:
                    return
                row.status = status
                row.result_summary = _safe_json(result) or {}
                row.error = error
                row.ended_at = datetime.utcnow()
                if mlflow_run_id is not None:
                    row.mlflow_run_id = mlflow_run_id
                if checkpoint is not None:
                    row.checkpoint = str(checkpoint)
                if isinstance(result, dict) and "metrics" in result:
                    metrics = result["metrics"]
                    if isinstance(metrics, dict):
                        for key in ("mean_reward", "total_reward", "sharpe", "max_drawdown",
                                    "final_value", "total_return"):
                            if key in metrics and getattr(row, key, None) is None:
                                try:
                                    setattr(row, key, float(metrics[key]))
                                except Exception:  # noqa: BLE001
                                    pass
        except Exception:  # noqa: BLE001
            logger.debug("Could not finalise rl_runs row", exc_info=True)

    def _stamp_tenancy(self, row: Any) -> None:
        ctx = self.context
        if ctx is None:
            return
        # AGENTS.md hard rule 34: copy ``experiment_id`` / ``test_id``
        # from the active :class:`RequestContext` onto every new
        # ``rl_runs`` / ``RLEpisode`` row. Alembic migration 0037 added
        # the columns; this stamper finally populates them so the
        # ``/experiments/...`` UI can join cleanly.
        for attr_ctx, attr_row in (
            ("user_id", "owner_user_id"),
            ("workspace_id", "workspace_id"),
            ("project_id", "project_id"),
            ("experiment_id", "experiment_id"),
            ("test_id", "test_id"),
        ):
            value = getattr(ctx, attr_ctx, None)
            if value and hasattr(row, attr_row) and getattr(row, attr_row, None) in (None, ""):
                setattr(row, attr_row, value)

    # ----------------------------------------------------------- trajectory store

    def _open_trajectory_store(self) -> None:
        if self.trajectory_store is not None:
            return
        if not self.persist_trajectories:
            self.trajectory_store = InMemoryTrajectoryStore()
            return
        store_spec = (self.spec.trajectory_store and self.spec.trajectory_store.spec) or None
        if store_spec is None:
            try:
                from aqp_rl.trajectories.iceberg_writer import IcebergTrajectoryStore

                self.trajectory_store = IcebergTrajectoryStore(run_id=self.run_id, context=self.context)
                return
            except Exception:  # noqa: BLE001
                logger.debug("falling back to in-memory trajectory store", exc_info=True)
                self.trajectory_store = InMemoryTrajectoryStore()
                return
        try:
            store = build_from_config(store_spec)
            if hasattr(store, "run_id"):
                store.run_id = self.run_id  # type: ignore[attr-defined]
            self.trajectory_store = store
        except Exception:  # noqa: BLE001
            logger.exception("trajectory_store construction failed; using in-memory")
            self.trajectory_store = InMemoryTrajectoryStore()

    def _close_trajectory_store(self) -> None:
        store = self.trajectory_store
        if store is None:
            return
        try:
            store.close()
        except Exception:  # noqa: BLE001
            logger.debug("trajectory store close failed", exc_info=True)

    def _record_step(
        self,
        *,
        episode: int,
        step: int,
        info: dict[str, Any],
        action: Any,
        reward: float,
    ) -> None:
        if self.trajectory_store is None:
            return
        try:
            ts_value = info.get("timestamp")
            self.trajectory_store.append_step(
                {
                    "run_id": self.run_id,
                    "episode": episode,
                    "step": step,
                    "ts": str(ts_value) if ts_value is not None else None,
                    "reward": float(reward),
                    "info": _flatten_info(info),
                }
            )
            pv = info.get("portfolio_value")
            if pv is not None:
                self.trajectory_store.append_equity(
                    {
                        "run_id": self.run_id,
                        "episode": episode,
                        "step": step,
                        "ts": str(ts_value) if ts_value is not None else None,
                        "portfolio_value": float(pv),
                        "drawdown": float(info.get("drawdown", 0.0) or 0.0),
                        "cash": float(info.get("cash", 0.0) or 0.0),
                    }
                )
            try:
                action_arr = list(map(float, action)) if hasattr(action, "__iter__") else [float(action)]
            except Exception:  # noqa: BLE001
                action_arr = []
            for i, val in enumerate(action_arr):
                self.trajectory_store.append_action(
                    {
                        "run_id": self.run_id,
                        "episode": episode,
                        "step": step,
                        "ts": str(ts_value) if ts_value is not None else None,
                        "asset_idx": i,
                        "action_value": float(val),
                    }
                )
            terms = info.get("reward_terms") or {}
            if isinstance(terms, dict) and terms:
                self.trajectory_store.append_reward_decomposition(
                    [
                        {
                            "run_id": self.run_id,
                            "episode": episode,
                            "step": step,
                            "ts": str(ts_value) if ts_value is not None else None,
                            "term_name": str(name),
                            "contribution": float(value),
                        }
                        for name, value in terms.items()
                    ]
                )
        except Exception:  # noqa: BLE001
            logger.debug("trajectory store append failed", exc_info=True)

    def _record_episode(self, *, episode: int, metrics: dict[str, Any]) -> None:
        try:
            from aqp.persistence.db import SessionLocal
            from aqp.persistence.models import RLEpisode

            with SessionLocal() as session:
                row = RLEpisode(
                    run_id=self.run_id,
                    episode=int(episode),
                    mean_reward=float(metrics.get("mean_reward", 0.0) or 0.0),
                    portfolio_value=metrics.get("final_value"),
                    length=int(metrics.get("length", 0) or 0),
                )
                self._stamp_tenancy(row)
                session.add(row)
                session.commit()
        except Exception:  # noqa: BLE001
            logger.debug("RLEpisode insert failed", exc_info=True)

    # ----------------------------------------------------------- core driver

    def _with_run(self, *, target: str, stage_message: str, action) -> RLRunResult:
        started = time.time()
        spec_id, version_id = self._snapshot_spec()
        run_db_id = self._open_run_row(target=target, version_id=version_id)
        self._db_run_id = run_db_id
        self._emit_progress(
            "start",
            stage_message,
            run_db_id=run_db_id,
            target=target,
            spec_id=spec_id,
            version_id=version_id,
        )
        status = "running"
        error: str | None = None
        result: dict[str, Any] = {}
        try:
            self._emit_progress("running", f"{stage_message} …", run_db_id=run_db_id)
            raw = action()
            if isinstance(raw, dict):
                result = raw
            elif raw is None:
                result = {}
            elif hasattr(raw, "to_dict"):
                result = raw.to_dict()
            else:
                result = {"value": str(raw)}
            status = "completed"
        except Exception as exc:  # noqa: BLE001
            logger.exception("RLRuntime action failed for %s", self.spec.name)
            status = "error"
            error = str(exc)
            if self.task_id:
                emit_error(self.task_id, error, context=self.context)
        finally:
            self._finalise_run_row(
                run_db_id,
                status=status,
                result=result,
                error=error,
                mlflow_run_id=result.get("mlflow_run_id") if isinstance(result, dict) else None,
                checkpoint=result.get("checkpoint") if isinstance(result, dict) else None,
            )
        if status == "completed" and self.task_id:
            emit_done(self.task_id, result, context=self.context)
        return RLRunResult(
            run_id=self.run_id,
            spec_id=spec_id,
            version_id=version_id,
            target=target,
            status=status,
            started_at=started,
            duration_ms=(time.time() - started) * 1000.0,
            task_id=self.task_id,
            mlflow_run_id=result.get("mlflow_run_id") if isinstance(result, dict) else None,
            checkpoint=result.get("checkpoint") if isinstance(result, dict) else None,
            metrics=result.get("metrics", {}) if isinstance(result, dict) else {},
            result=result if isinstance(result, dict) else {"value": str(result)},
            error=error,
        )

    # ----------------------------------------------------------- progress

    def _emit_progress(self, stage: str, message: str, **extra: Any) -> None:
        logger.info("[rl:%s] %s: %s", self.spec.slug, stage, message)
        if not self.task_id:
            return
        emit(
            self.task_id,
            stage,
            message,
            context=self.context,
            run_id=self.run_id,
            spec_slug=self.spec.slug,
            **extra,
        )


def runtime_for(spec_or_name: Any, **kwargs: Any) -> RLRuntime:
    """Build a runtime from an :class:`RLExperimentSpec` instance or a slug."""
    if isinstance(spec_or_name, RLExperimentSpec):
        spec = spec_or_name
    else:
        from aqp_rl.registry import get_rl_spec

        spec = get_rl_spec(str(spec_or_name))
    return RLRuntime(spec, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarise_history(rewards: list[float], history: list[float]) -> dict[str, float]:
    """Compact metrics dict mirroring :func:`aqp_rl.evaluator.summarise`."""
    metrics: dict[str, float] = {
        "mean_reward": float(sum(rewards) / max(len(rewards), 1)),
        "total_reward": float(sum(rewards)),
        "length": float(len(rewards)),
    }
    if history:
        first = float(history[0]) or 1.0
        last = float(history[-1])
        metrics["initial_value"] = first
        metrics["final_value"] = last
        metrics["total_return"] = float((last - first) / first)
        peak = first
        max_dd = 0.0
        for v in history:
            peak = max(peak, float(v))
            max_dd = min(max_dd, (float(v) - peak) / peak if peak else 0.0)
        metrics["max_drawdown"] = float(max_dd)
        if len(history) > 1:
            import math

            rets = []
            for prev, curr in zip(history[:-1], history[1:], strict=False):
                if prev > 0:
                    rets.append((curr - prev) / prev)
            if rets:
                mean_r = sum(rets) / len(rets)
                var = sum((r - mean_r) ** 2 for r in rets) / max(len(rets) - 1, 1)
                std_r = math.sqrt(var)
                metrics["sharpe"] = float(math.sqrt(252) * mean_r / std_r) if std_r > 0 else 0.0
    return metrics


def _flatten_info(info: dict[str, Any]) -> dict[str, Any]:
    """Drop non-serialisable fields from info before storing."""
    out: dict[str, Any] = {}
    for k, v in (info or {}).items():
        if k in ("reward_terms",):
            continue
        try:
            import json

            json.dumps(v, default=str)
            out[k] = v
        except Exception:
            out[k] = str(v)[:500]
    return out


def _safe_json(value: Any) -> Any:
    import json

    try:
        json.dumps(value, default=str)
        return value
    except Exception:
        return {"_unserialisable": str(value)[:1000]}


__all__ = [
    "RLRunResult",
    "RLRuntime",
    "runtime_for",
]
