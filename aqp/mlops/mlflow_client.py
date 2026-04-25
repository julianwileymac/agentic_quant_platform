"""MLflow tracking helpers — experiment bootstrap, backtest logging, lineage."""
from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from aqp.config import settings

logger = logging.getLogger(__name__)


def _client():
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    return mlflow


def ensure_experiment(name: str | None = None) -> str:
    import mlflow

    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    exp = mlflow.set_experiment(name or settings.mlflow_experiment)
    return exp.experiment_id


def experiment_name_for_strategy(strategy_id: str | None) -> str:
    """Return the canonical MLflow experiment name for a strategy row.

    We key off the ``strategy_id`` UUID (trimmed to 8 chars) so a strategy's
    entire lifecycle — backtest runs, WFO nests, paper sessions, ML training
    runs — shares a single experiment page.
    """
    if not strategy_id:
        return settings.mlflow_experiment
    return f"strategy/{strategy_id[:8]}"


def log_backtest(
    run_name: str,
    summary: dict[str, Any],
    strategy_cfg: dict[str, Any],
    equity_curve: pd.Series,
    dataset_hash: str | None = None,
    strategy_id: str | None = None,
    engine: str | None = None,
) -> str:
    """Create an MLflow run for a backtest and log metrics + config + equity csv.

    If ``strategy_id`` is provided, the run is filed under a dedicated
    ``strategy/<id>`` experiment so the Strategy Browser can deep-link into
    the full run history for that strategy.
    """
    mlflow = _client()
    ensure_experiment(experiment_name_for_strategy(strategy_id))

    with mlflow.start_run(run_name=run_name) as run:
        for metric in ("sharpe", "sortino", "max_drawdown", "total_return", "final_equity", "calmar"):
            if metric in summary and summary[metric] is not None:
                with contextlib.suppress(Exception):
                    mlflow.log_metric(metric, float(summary[metric]))

        mlflow.log_params(_flatten_params(strategy_cfg))
        if dataset_hash:
            mlflow.set_tag("dataset_hash", dataset_hash)
        if strategy_id:
            mlflow.set_tag("aqp.strategy_id", strategy_id)
        if engine:
            mlflow.set_tag("aqp.engine", engine)
        mlflow.set_tag("aqp.component", "backtest")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            equity_file = path / "equity_curve.csv"
            equity_curve.to_csv(equity_file, header=["equity"])
            mlflow.log_artifact(str(equity_file))

            cfg_file = path / "strategy_config.json"
            cfg_file.write_text(json.dumps(strategy_cfg, default=str, indent=2))
            mlflow.log_artifact(str(cfg_file))

        return run.info.run_id


def link_strategy(run_id: str, strategy_id: str) -> None:
    """Attach an ``aqp.strategy_id`` tag to an existing run (for after-the-fact
    wiring when the strategy row is created after the backtest run)."""
    try:
        mlflow = _client()
        from mlflow.tracking import MlflowClient

        MlflowClient(tracking_uri=settings.mlflow_tracking_uri).set_tag(
            run_id, "aqp.strategy_id", strategy_id
        )
    except Exception:
        logger.debug("link_strategy failed", exc_info=True)


def _flatten_params(config: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (config or {}).items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_params(v, key))
        elif isinstance(v, (list, tuple)):
            out[key] = ",".join(str(x) for x in v)
        else:
            out[key] = str(v)
    return {k[:250]: v[:500] for k, v in out.items()}


# ---------------------------------------------------------------------------
# Extended logging helpers (paper / WFO / factor / strategy / alpha training)
# ---------------------------------------------------------------------------


def log_paper_session(
    result: dict[str, Any],
    config: dict[str, Any],
    dataset_hash: str | None = None,
) -> str | None:
    """Log a paper-session result as its own MLflow run."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=f"paper-{result.get('run_name', 'adhoc')}") as run:
            for metric in (
                "final_equity",
                "realized_pnl",
                "bars_seen",
                "orders_submitted",
                "fills",
            ):
                val = result.get(metric)
                if val is None:
                    continue
                with contextlib.suppress(Exception):
                    mlflow.log_metric(metric, float(val))
            mlflow.log_params(_flatten_params(config))
            if dataset_hash:
                mlflow.set_tag("dataset_hash", dataset_hash)
            mlflow.set_tag("aqp.component", "paper")
            return run.info.run_id
    except Exception:
        logger.exception("log_paper_session failed")
        return None


def log_walkforward(
    summary_per_window: list[dict[str, Any]],
    final_oos_sharpe: float | None,
    run_name: str = "wfo",
) -> str | None:
    """Log a walk-forward optimisation: parent run + per-window nested runs."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=run_name) as parent:
            mlflow.set_tag("aqp.component", "walk_forward")
            if final_oos_sharpe is not None:
                with contextlib.suppress(Exception):
                    mlflow.log_metric("oos_sharpe", float(final_oos_sharpe))
            for i, window in enumerate(summary_per_window):
                try:
                    with mlflow.start_run(
                        run_name=f"{run_name}-w{i}", nested=True
                    ):
                        for k, v in (window or {}).items():
                            if isinstance(v, (int, float)):
                                try:
                                    mlflow.log_metric(k, float(v))
                                except Exception:
                                    continue
                            else:
                                mlflow.log_param(k, str(v))
                except Exception:
                    logger.exception("nested WFO window log failed")
            return parent.info.run_id
    except Exception:
        logger.exception("log_walkforward failed")
        return None


def log_factor_run(
    factor_name: str,
    ic_stats: dict[str, dict[str, float]],
    cumulative_returns: pd.DataFrame | None = None,
    turnover_mean: float | None = None,
    tear_sheet_html: str | None = None,
) -> str | None:
    """Log an Alphalens-style factor evaluation."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=f"factor-{factor_name}") as run:
            mlflow.set_tag("aqp.component", "factor_eval")
            mlflow.set_tag("factor", factor_name)
            for horizon, stats in (ic_stats or {}).items():
                for stat_name, val in (stats or {}).items():
                    try:
                        mlflow.log_metric(f"ic_{horizon}_{stat_name}", float(val))
                    except Exception:
                        continue
            if turnover_mean is not None:
                with contextlib.suppress(Exception):
                    mlflow.log_metric("turnover_mean", float(turnover_mean))
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp)
                if cumulative_returns is not None and not cumulative_returns.empty:
                    cr = path / "cumulative_returns.csv"
                    cumulative_returns.to_csv(cr)
                    mlflow.log_artifact(str(cr))
                if tear_sheet_html:
                    ts = path / "tear_sheet.html"
                    ts.write_text(tear_sheet_html, encoding="utf-8")
                    mlflow.log_artifact(str(ts))
            return run.info.run_id
    except Exception:
        logger.exception("log_factor_run failed")
        return None


def log_strategy_version(
    strategy_id: str,
    version: int,
    config_yaml: str,
    dataset_hash: str | None = None,
) -> str | None:
    """Log a strategy version promotion as an MLflow run."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=f"strategy-{strategy_id[:8]}-v{version}") as run:
            mlflow.set_tag("aqp.component", "strategy_version")
            mlflow.set_tag("strategy_id", strategy_id)
            mlflow.log_param("version", version)
            if dataset_hash:
                mlflow.set_tag("dataset_hash", dataset_hash)
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "config.yaml"
                path.write_text(config_yaml, encoding="utf-8")
                mlflow.log_artifact(str(path))
            return run.info.run_id
    except Exception:
        logger.exception("log_strategy_version failed")
        return None


def log_alpha_training(
    alpha_class: str,
    hyperparams: dict[str, Any],
    metrics: dict[str, Any],
    feature_importance: dict[str, float] | None = None,
    model_path: str | Path | None = None,
) -> str | None:
    """Log an ML alpha training run."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=f"alpha-{alpha_class}") as run:
            mlflow.set_tag("aqp.component", "alpha_training")
            mlflow.set_tag("alpha_class", alpha_class)
            mlflow.log_params(_flatten_params(hyperparams))
            for k, v in (metrics or {}).items():
                if isinstance(v, (int, float)):
                    try:
                        mlflow.log_metric(k, float(v))
                    except Exception:
                        continue
            if feature_importance:
                with tempfile.TemporaryDirectory() as tmp:
                    fi = Path(tmp) / "feature_importance.json"
                    fi.write_text(json.dumps(feature_importance, indent=2))
                    mlflow.log_artifact(str(fi))
            if model_path is not None:
                with contextlib.suppress(Exception):
                    mlflow.log_artifact(str(model_path))
            return run.info.run_id
    except Exception:
        logger.exception("log_alpha_training failed")
        return None


def log_feature_engineering(
    features_df: pd.DataFrame,
    dataset_hash: str | None = None,
    engineer_config: dict[str, Any] | None = None,
) -> str | None:
    """Log a feature-engineering step as an MLflow run."""
    try:
        mlflow = _client()
        ensure_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name="features") as run:
            mlflow.set_tag("aqp.component", "feature_engineering")
            if dataset_hash:
                mlflow.set_tag("dataset_hash", dataset_hash)
            mlflow.log_params(_flatten_params(engineer_config or {}))
            mlflow.log_metric("feature_rows", float(len(features_df)))
            mlflow.log_metric("feature_columns", float(len(features_df.columns)))
            return run.info.run_id
    except Exception:
        logger.exception("log_feature_engineering failed")
        return None


# ---------------------------------------------------------------------------
# Model-registry + serving helpers.
# ---------------------------------------------------------------------------


def register_and_serve(
    model_uri: str,
    name: str,
    backend: str = "mlflow",
    stage: str = "Staging",
    **backend_kwargs: Any,
) -> dict[str, Any]:
    """Push a model to the Registry under ``name`` and deploy it via ``backend``.

    ``backend`` ∈ ``{"mlflow", "ray", "torchserve"}`` — each maps to the
    corresponding adapter in :mod:`aqp.mlops.serving`. Returns a dict
    with the new version number, registry URI, and the backend's
    :class:`DeploymentInfo` payload.

    No-op + logs an error when MLflow / the backend is unavailable.
    """
    try:
        mlflow = _client()
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
        try:
            client.create_registered_model(name)
        except Exception:
            logger.debug("registered model %s already exists", name)
        version = client.create_model_version(name=name, source=model_uri, run_id=None)
        try:
            client.transition_model_version_stage(
                name=name,
                version=version.version,
                stage=stage,
                archive_existing_versions=stage == "Production",
            )
        except Exception:
            logger.debug("transition_model_version_stage failed", exc_info=True)

        registry_uri = f"models:/{name}/{stage}"
        deployment_info: dict[str, Any] = {}
        try:
            from aqp.mlops.serving.base import resolve_model

            prepared = resolve_model(registry_uri)
            if backend == "mlflow":
                from aqp.mlops.serving.mlflow_serve import MLflowServeDeployment

                info = MLflowServeDeployment(**backend_kwargs).deploy(prepared)
            elif backend == "ray":
                from aqp.mlops.serving.ray_serve import RayServeDeployment

                info = RayServeDeployment(**backend_kwargs).deploy(prepared)
            elif backend in {"torchserve", "torch"}:
                from aqp.mlops.serving.torchserve import TorchServeDeployment

                info = TorchServeDeployment(**backend_kwargs).deploy(prepared, model_name=name)
            else:
                raise ValueError(f"Unknown backend {backend!r}")
            deployment_info = {
                "backend": info.backend,
                "endpoint_url": info.endpoint_url,
                "pid": info.pid,
                "metadata": info.metadata,
            }
        except Exception:
            logger.exception("deployment via %s failed", backend)

        return {
            "name": name,
            "version": version.version,
            "stage": stage,
            "registry_uri": registry_uri,
            "source": model_uri,
            "deployment": deployment_info,
        }
    except Exception:
        logger.exception("register_and_serve failed for %s", name)
        return {"name": name, "error": "mlflow unavailable"}


def promote_to_production(name: str, version: int | str) -> bool:
    """Transition ``(name, version)`` to Production, archiving prior versions."""
    try:
        _ = _client()
        from mlflow.tracking import MlflowClient

        client = MlflowClient(tracking_uri=settings.mlflow_tracking_uri)
        client.transition_model_version_stage(
            name=name,
            version=str(version),
            stage="Production",
            archive_existing_versions=True,
        )
        return True
    except Exception:
        logger.exception("promote_to_production failed for %s v%s", name, version)
        return False
