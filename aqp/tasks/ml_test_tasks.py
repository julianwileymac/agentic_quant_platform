"""Celery tasks for the interactive ML testing workbench.

Backs the ``/ml/test/*`` endpoints in :mod:`aqp.api.routes.ml`. All
tasks route to the ``ml`` queue, emit progress through
:mod:`aqp.tasks._progress`, and re-use existing alpha plumbing
(`DeployedModelAlpha` + `DuckDBHistoryProvider`) so production code paths
are exercised by the test runs.

Four task families:

- ``predict_single`` — single-row inference, sub-second sync.
- ``predict_batch`` — many rows from an Iceberg slice / uploaded CSV.
- ``compare_models`` — A/B between two model versions on the same data.
- ``scenario_perturbation`` — sensitivity table for ±N% perturbations
  of every input feature.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

import numpy as np
import pandas as pd

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _load_alpha(deployment_id: str) -> Any:
    """Build a :class:`aqp.strategies.ml_alphas.DeployedModelAlpha` and load it."""
    from aqp.strategies.ml_alphas import DeployedModelAlpha

    alpha = DeployedModelAlpha(deployment_id=deployment_id)
    alpha._ensure_loaded()  # noqa: SLF001 - intentional warm-up
    return alpha


def _signals_to_rows(signals: list[Any], cap: int) -> list[dict[str, Any]]:
    rows = []
    for sig in signals[: int(cap)]:
        rows.append(
            {
                "vt_symbol": sig.symbol.vt_symbol,
                "direction": sig.direction.value if hasattr(sig.direction, "value") else str(sig.direction),
                "strength": float(sig.strength),
                "confidence": float(sig.confidence),
                "timestamp": str(sig.timestamp),
                "rationale": sig.rationale,
            }
        )
    return rows


@celery_app.task(bind=True, name="aqp.tasks.ml_test_tasks.predict_single")
def predict_single(
    self,
    *,
    deployment_id: str,
    feature_row: dict[str, Any],
    vt_symbol: str | None = None,
) -> dict[str, Any]:
    """Score a single feature row against a deployed model.

    ``feature_row`` is a flat ``{column: value}`` dict. The wrapper
    builds a one-row DataFrame and runs it through the deployed alpha's
    ``_predict`` path so sklearn/torch/dataset-backed models all work.
    """
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Single-row prediction for deployment {deployment_id}")
    try:
        alpha = _load_alpha(deployment_id)
        if alpha._model is None:  # noqa: SLF001
            raise RuntimeError("Deployment did not resolve to a usable model")
        frame = pd.DataFrame([feature_row])
        try:
            preds = alpha._predict(frame.to_numpy(dtype=float))  # noqa: SLF001
        except Exception:
            # Fall back to the model's bare predict() for non-numpy paths.
            preds = alpha._model.predict(frame)
        value = float(np.asarray(preds, dtype=float).reshape(-1)[0])
        result = {
            "deployment_id": deployment_id,
            "vt_symbol": vt_symbol,
            "prediction": value,
            "feature_row": feature_row,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("predict_single failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ml_test_tasks.predict_batch")
def predict_batch(
    self,
    *,
    deployment_id: str,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    last_n: int = 200,
    iceberg_identifier: str | None = None,
) -> dict[str, Any]:
    """Run inference over an Iceberg slice and return a sample of signals."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Batch prediction for deployment {deployment_id}")
    try:
        from aqp.config import settings
        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider
        from aqp.strategies.ml_alphas import DeployedModelAlpha

        parsed = [
            Symbol.parse(s) if "." in s else Symbol(ticker=s)
            for s in (symbols or settings.universe_list or [])
        ]
        if not parsed:
            raise ValueError("symbols is required")
        start_ts = pd.Timestamp(start or settings.default_start)
        end_ts = pd.Timestamp(end or settings.default_end)
        provider = DuckDBHistoryProvider()
        bars = provider.get_bars(parsed, start=start_ts, end=end_ts)
        if bars.empty:
            raise RuntimeError(
                f"No bars between {start_ts.date()} and {end_ts.date()} for {symbols}"
            )
        alpha = DeployedModelAlpha(deployment_id=deployment_id)
        emit(task_id, "running", f"Scoring {len(bars)} bars")
        signals = alpha.generate_signals(
            bars=bars, universe=parsed, context={"current_time": end_ts}
        )
        rows = _signals_to_rows(signals, last_n)
        result = {
            "deployment_id": deployment_id,
            "n_bars": int(len(bars)),
            "n_signals": int(len(signals)),
            "iceberg_identifier": iceberg_identifier,
            "signals": rows,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("predict_batch failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ml_test_tasks.compare_models")
def compare_models(
    self,
    *,
    deployment_id_a: str,
    deployment_id_b: str,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    last_n: int = 200,
) -> dict[str, Any]:
    """Run two deployed models on the same bars and compute a side-by-side diff."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(
        task_id,
        "start",
        f"Comparing deployments {deployment_id_a} vs {deployment_id_b}",
    )
    try:
        from aqp.config import settings
        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider
        from aqp.strategies.ml_alphas import DeployedModelAlpha

        parsed = [
            Symbol.parse(s) if "." in s else Symbol(ticker=s)
            for s in (symbols or settings.universe_list or [])
        ]
        if not parsed:
            raise ValueError("symbols is required")
        start_ts = pd.Timestamp(start or settings.default_start)
        end_ts = pd.Timestamp(end or settings.default_end)
        bars = DuckDBHistoryProvider().get_bars(parsed, start=start_ts, end=end_ts)
        if bars.empty:
            raise RuntimeError("No bars for compare window")

        alpha_a = DeployedModelAlpha(deployment_id=deployment_id_a)
        alpha_b = DeployedModelAlpha(deployment_id=deployment_id_b)
        ctx = {"current_time": end_ts}

        signals_a = alpha_a.generate_signals(bars=bars, universe=parsed, context=ctx)
        signals_b = alpha_b.generate_signals(bars=bars, universe=parsed, context=ctx)
        rows_a = _signals_to_rows(signals_a, last_n)
        rows_b = _signals_to_rows(signals_b, last_n)

        agree = 0
        disagree = 0
        for sa in rows_a:
            for sb in rows_b:
                if sa["vt_symbol"] == sb["vt_symbol"] and sa["timestamp"] == sb["timestamp"]:
                    if sa["direction"] == sb["direction"]:
                        agree += 1
                    else:
                        disagree += 1
                    break
        comparison = {
            "n_signals_a": int(len(signals_a)),
            "n_signals_b": int(len(signals_b)),
            "agreement_count": int(agree),
            "disagreement_count": int(disagree),
            "agreement_rate": (
                float(agree / (agree + disagree)) if (agree + disagree) else None
            ),
        }
        result = {
            "deployment_id_a": deployment_id_a,
            "deployment_id_b": deployment_id_b,
            "n_bars": int(len(bars)),
            "comparison": comparison,
            "signals_a": rows_a,
            "signals_b": rows_b,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("compare_models failed")
        emit_error(task_id, str(e))
        raise


@celery_app.task(bind=True, name="aqp.tasks.ml_test_tasks.scenario_perturbation")
def scenario_perturbation(
    self,
    *,
    deployment_id: str,
    feature_row: dict[str, float],
    perturbations: list[float] | None = None,
) -> dict[str, Any]:
    """Sensitivity analysis: perturb each input feature by ``perturbations``.

    Returns a table of ``{feature, perturbation, prediction, delta}``
    so the webui can render a heatmap of feature importance for the
    given input.
    """
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    emit(task_id, "start", f"Scenario sweep for deployment {deployment_id}")
    try:
        alpha = _load_alpha(deployment_id)
        if alpha._model is None:  # noqa: SLF001
            raise RuntimeError("Deployment did not resolve to a usable model")
        perturbations = list(perturbations or [-0.1, -0.05, 0.0, 0.05, 0.1])
        baseline_frame = pd.DataFrame([feature_row])
        try:
            baseline = float(
                np.asarray(
                    alpha._predict(baseline_frame.to_numpy(dtype=float)),  # noqa: SLF001
                    dtype=float,
                ).reshape(-1)[0]
            )
        except Exception:
            baseline = float(
                np.asarray(alpha._model.predict(baseline_frame), dtype=float).reshape(-1)[0]
            )

        rows: list[dict[str, Any]] = []
        for feat, baseline_value in feature_row.items():
            for pct in perturbations:
                perturbed = dict(feature_row)
                try:
                    perturbed[feat] = float(baseline_value) * (1.0 + float(pct))
                except (TypeError, ValueError):
                    perturbed[feat] = float(pct)
                frame = pd.DataFrame([perturbed])
                try:
                    score = float(
                        np.asarray(
                            alpha._predict(frame.to_numpy(dtype=float)),  # noqa: SLF001
                            dtype=float,
                        ).reshape(-1)[0]
                    )
                except Exception:
                    score = float(
                        np.asarray(alpha._model.predict(frame), dtype=float).reshape(-1)[0]
                    )
                rows.append(
                    {
                        "feature": feat,
                        "perturbation": float(pct),
                        "prediction": score,
                        "delta": float(score - baseline),
                    }
                )

        result = {
            "deployment_id": deployment_id,
            "baseline_prediction": baseline,
            "perturbations": perturbations,
            "rows": rows,
        }
        emit_done(task_id, result)
        return result
    except Exception as e:
        logger.exception("scenario_perturbation failed")
        emit_error(task_id, str(e))
        raise
