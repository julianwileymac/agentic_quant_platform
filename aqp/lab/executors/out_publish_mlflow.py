"""``out.publish_mlflow`` — register a run artifact with MLflow.

Routes through the canonical MLflow tracking URI from
:attr:`settings.mlflow_tracking_uri` (read once via the cached
:class:`Settings` singleton, AGENTS rule 7). Degrades cleanly when
MLflow isn't installed so the executor stays importable in dev.
"""
from __future__ import annotations

import logging
from typing import Any

from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    experiment = str(params.get("experiment") or "lab-default")
    run_name = str(params.get("run_name") or f"lab-run-{ctx.run_id}")

    # Pull whatever metrics / artifacts the upstream provided.
    upstream_metrics: dict[str, Any] = {}
    upstream_artifact_uri: str | None = None
    for locator in (ctx.upstream or {}).values():
        if isinstance(locator, dict):
            stats = locator.get("stats") or {}
            if isinstance(stats, dict):
                for k, v in stats.items():
                    try:
                        upstream_metrics[str(k)] = float(v)
                    except Exception:  # noqa: BLE001
                        continue
            uri = locator.get("uri")
            if not upstream_artifact_uri and isinstance(uri, str):
                upstream_artifact_uri = uri

    try:
        from aqp.config import settings
        import mlflow  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        return NodeResult(
            status="error",
            error=f"mlflow unavailable: {exc}",
            log_label="mlflow_unavailable",
        )

    try:
        mlflow_uri = getattr(settings, "mlflow_tracking_uri", None)
        if mlflow_uri:
            mlflow.set_tracking_uri(mlflow_uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name) as run:
            for k, v in upstream_metrics.items():
                try:
                    mlflow.log_metric(k.replace(" ", "_"), v)
                except Exception:  # noqa: BLE001
                    continue
            mlflow.log_param("lab_run_id", ctx.run_id)
            mlflow.log_param("lab_node_id", ctx.node_id)
            mlflow_run_id = run.info.run_id
    except Exception as exc:  # noqa: BLE001
        return NodeResult(status="error", error=f"mlflow publish failed: {exc}")

    return NodeResult(
        status="done",
        output_locator={
            "kind": "mlflow_run",
            "experiment": experiment,
            "mlflow_run_id": mlflow_run_id,
            "node_id": node.id,
        },
        metrics={"mlflow_run_id": mlflow_run_id, "n_metrics": len(upstream_metrics)},
        log_label=f"mlflow:{experiment}/{mlflow_run_id[:8]}",
    )
