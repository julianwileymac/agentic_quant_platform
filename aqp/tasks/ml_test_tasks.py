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

import json
import logging
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from aqp.backtest.metrics import max_drawdown, sharpe_ratio
from aqp.metadata import parse_urn, write_aspect
from aqp.metadata.aspect_lookup import load_ml_model
from aqp.metadata.openmetadata import MlHyperParameter, MlTestResult
from aqp.persistence.db import get_session
from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

if TYPE_CHECKING:
    from aqp.core.types import Symbol

logger = logging.getLogger(__name__)


def _coerce_hyperparameter_value(parameter: MlHyperParameter) -> Any:
    """Parse a typed hyperparameter value from its string payload."""
    value_raw = parameter.value
    value_type = parameter.value_type.strip().lower()
    try:
        if value_type in {"int", "integer"}:
            return int(value_raw)
        if value_type in {"float", "double"}:
            return float(value_raw)
        if value_type in {"bool", "boolean"}:
            return value_raw.strip().lower() in {"1", "true", "yes", "y", "on"}
        if value_type in {"json", "dict", "list"}:
            return json.loads(value_raw)
    except Exception:  # noqa: BLE001
        logger.debug(
            "Could not parse hyperparameter %s as %s; keeping raw string",
            parameter.name,
            parameter.value_type,
            exc_info=True,
        )
    return value_raw


def _hyperparameters_to_dict(hyperparameters: list[MlHyperParameter]) -> dict[str, Any]:
    """Convert ``MlHyperParameter`` rows into a plain dict."""
    return {
        hp.name: _coerce_hyperparameter_value(hp)
        for hp in hyperparameters
    }


def _resolve_model_urn(config: dict[str, Any], model_urn: str | None) -> str | None:
    """Resolve a model URN from explicit input or inline config."""
    model_cfg = config.get("model")
    candidates: list[Any] = [
        model_urn,
        config.get("model_urn"),
        config.get("urn"),
    ]
    if isinstance(model_cfg, dict):
        candidates.extend((model_cfg.get("model_urn"), model_cfg.get("urn")))
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        urn = candidate.strip()
        if not urn:
            continue
        try:
            parse_urn(urn)
            return urn
        except ValueError:
            logger.info("Ignoring non-canonical model URN candidate: %s", urn)
    return None


def _extract_inline_model_config(
    config: dict[str, Any],
) -> tuple[str, dict[str, Any], str | None]:
    """Read algorithm/hyperparameters/target from inline config."""
    model_cfg = config.get("model")
    model_cfg_dict = model_cfg if isinstance(model_cfg, dict) else {}
    algorithm = str(
        config.get("algorithm")
        or model_cfg_dict.get("algorithm")
        or model_cfg_dict.get("class")
        or "unknown"
    )
    hyperparameters = config.get("hyperparameters")
    if not isinstance(hyperparameters, dict):
        kwargs = model_cfg_dict.get("kwargs")
        hyperparameters = kwargs if isinstance(kwargs, dict) else {}
    target_raw = config.get("target") or model_cfg_dict.get("target")
    target = str(target_raw) if target_raw is not None else None
    return algorithm, dict(hyperparameters), target


def _coerce_float_list(values: Any) -> list[float]:
    """Best-effort conversion of list-like inputs to floats."""
    if values is None:
        return []
    if isinstance(values, np.ndarray):
        values = values.tolist()
    if not isinstance(values, (list, tuple)):
        return []
    out: list[float] = []
    for value in values:
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            continue
    return out


def _read_metric(config: dict[str, Any], *keys: str) -> float | None:
    """Return the first parseable metric value from config/metrics dict."""
    metrics_block = config.get("metrics")
    metrics = metrics_block if isinstance(metrics_block, dict) else {}
    for key in keys:
        for source in (config, metrics):
            if key not in source:
                continue
            try:
                return float(source[key])
            except (TypeError, ValueError):
                continue
    return None


def _compute_test_metrics(config: dict[str, Any]) -> dict[str, Any]:
    """Compute sharpe/max drawdown/agreement/accuracy from test inputs."""
    predictions = _coerce_float_list(
        config.get("predictions") or config.get("scores") or config.get("signal_scores")
    )
    labels = _coerce_float_list(config.get("labels") or config.get("actual"))
    returns = _coerce_float_list(
        config.get("returns") or config.get("strategy_returns")
    )
    if not returns and predictions:
        returns = list(predictions)

    sharpe_value = _read_metric(config, "sharpe_ratio", "sharpe")
    max_drawdown_value = _read_metric(config, "max_drawdown")
    if returns and sharpe_value is None:
        returns_series = pd.Series(returns, dtype=float)
        sharpe_value = float(sharpe_ratio(returns_series))
    if returns and max_drawdown_value is None:
        equity_curve = (1.0 + pd.Series(returns, dtype=float)).cumprod()
        max_drawdown_value = float(max_drawdown(equity_curve))

    agreement_rate = _read_metric(config, "agreement_rate")
    accuracy = _read_metric(config, "accuracy")
    if predictions and labels and (agreement_rate is None or accuracy is None):
        n = min(len(predictions), len(labels))
        if n > 0:
            pred_arr = np.asarray(predictions[:n], dtype=float)
            label_arr = np.asarray(labels[:n], dtype=float)
            if agreement_rate is None:
                agreement_rate = float(np.mean(np.sign(pred_arr) == np.sign(label_arr)))
            if accuracy is None:
                if str(config.get("problem_type", "")).lower() == "classification":
                    accuracy = float(
                        np.mean((pred_arr >= 0).astype(int) == (label_arr >= 0).astype(int))
                    )
                else:
                    accuracy = agreement_rate

    return {
        "sharpe_ratio": sharpe_value,
        "max_drawdown": max_drawdown_value,
        "agreement_rate": agreement_rate,
        "accuracy": accuracy,
        "n_predictions": len(predictions),
        "n_labels": len(labels),
        "n_returns": len(returns),
    }


def _write_ml_test_result(
    *,
    model_urn: str,
    test_id: str,
    started_at: datetime,
    completed_at: datetime,
    sharpe_value: float | None,
    max_drawdown_value: float | None,
    agreement_rate: float | None,
    accuracy: float | None,
    extra_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Persist a ``mlTestResult`` aspect and return identifying metadata."""
    payload = MlTestResult(
        model_urn=model_urn,
        test_id=test_id,
        started_at=started_at,
        completed_at=completed_at,
        sharpe_ratio=sharpe_value,
        max_drawdown=max_drawdown_value,
        agreement_rate=agreement_rate,
        accuracy=accuracy,
        extra_metrics=extra_metrics,
    )
    with get_session() as session:
        row = write_aspect(session, model_urn, "mlTestResult", payload)
        aspect_id = str(row.id)
        aspect_version = int(row.version)
    logger.info(
        "Persisted mlTestResult aspect for %s (id=%s version=%s)",
        model_urn,
        aspect_id,
        aspect_version,
    )
    return {"aspect_id": aspect_id, "version": aspect_version}


@celery_app.task(bind=True, name="aqp.tasks.ml_test_tasks.run_ml_test")
def run_ml_test(
    self,
    *,
    config: dict[str, Any] | None = None,
    model_urn: str | None = None,
) -> dict[str, Any]:
    """Run a config-driven ML test and optionally persist ``mlTestResult``."""
    task_id = self.request.id or f"local-{uuid.uuid4().hex[:8]}"
    test_config = dict(config or {})
    started_at = datetime.utcnow()
    resolved_model_urn = _resolve_model_urn(test_config, model_urn)
    algorithm, hyperparameters, target = _extract_inline_model_config(test_config)
    emit(task_id, "start", "Running ML test workload")
    try:
        if model_urn:
            model = load_ml_model(model_urn)
            if model is None:
                raise ValueError(f"MlModel aspect not found for {model_urn}")
            algorithm = model.algorithm
            hyperparameters = _hyperparameters_to_dict(model.ml_hyper_parameters)
            target = model.target
            resolved_model_urn = model_urn
            logger.info(
                "run_ml_test using metadata aspect model path for %s",
                model_urn,
            )
        else:
            logger.info("run_ml_test using inline config path")

        emit(task_id, "running", f"Computing test metrics for {algorithm}")
        metrics = _compute_test_metrics(test_config)
        completed_at = datetime.utcnow()
        extra_metrics: dict[str, Any] = {
            "algorithm": algorithm,
            "target": target,
            "hyperparameters": hyperparameters,
            "n_predictions": metrics["n_predictions"],
            "n_labels": metrics["n_labels"],
            "n_returns": metrics["n_returns"],
        }
        extra_from_config = test_config.get("extra_metrics")
        if isinstance(extra_from_config, dict):
            extra_metrics.update(extra_from_config)

        aspect_meta: dict[str, Any] | None = None
        if resolved_model_urn:
            aspect_meta = _write_ml_test_result(
                model_urn=resolved_model_urn,
                test_id=task_id,
                started_at=started_at,
                completed_at=completed_at,
                sharpe_value=metrics["sharpe_ratio"],
                max_drawdown_value=metrics["max_drawdown"],
                agreement_rate=metrics["agreement_rate"],
                accuracy=metrics["accuracy"],
                extra_metrics=extra_metrics,
            )

        result = {
            "test_id": task_id,
            "model_urn": resolved_model_urn,
            "algorithm": algorithm,
            "target": target,
            "hyperparameters": hyperparameters,
            "sharpe_ratio": metrics["sharpe_ratio"],
            "max_drawdown": metrics["max_drawdown"],
            "agreement_rate": metrics["agreement_rate"],
            "accuracy": metrics["accuracy"],
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "ml_test_result_aspect": aspect_meta,
        }
        emit_done(task_id, result)
        return result
    except Exception as exc:
        completed_at = datetime.utcnow()
        if resolved_model_urn:
            try:
                _write_ml_test_result(
                    model_urn=resolved_model_urn,
                    test_id=task_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    sharpe_value=None,
                    max_drawdown_value=None,
                    agreement_rate=None,
                    accuracy=None,
                    extra_metrics={
                        "algorithm": algorithm,
                        "target": target,
                        "hyperparameters": hyperparameters,
                        "error": str(exc),
                    },
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to persist error mlTestResult aspect for %s",
                    resolved_model_urn,
                )
        logger.exception("run_ml_test failed")
        emit_error(task_id, str(exc))
        raise


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


def _load_iceberg_slice(
    iceberg_identifier: str,
    *,
    symbols: list[Symbol],
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
) -> pd.DataFrame:
    """Load a slice of an Iceberg table as a tidy bars dataframe.

    All reads go through :func:`aqp.data.iceberg_catalog.read_arrow`
    (AGENTS.md rule 3). We do best-effort row-filtering by symbol /
    timestamp columns when they look like the standard medallion-bar
    schema (``vt_symbol``, ``timestamp`` / ``ts``).
    """
    from aqp.data import iceberg_catalog

    arrow_tbl = iceberg_catalog.read_arrow(iceberg_identifier)
    frame = arrow_tbl.to_pandas()
    if frame.empty:
        return frame
    # Symbol filter — accept ``vt_symbol`` or ``symbol`` columns.
    vt_col = next(
        (c for c in ("vt_symbol", "symbol", "ticker") if c in frame.columns),
        None,
    )
    if vt_col and symbols:
        wanted = {s.vt_symbol for s in symbols}
        # Fall back to ticker-only equality when vt_symbol isn't dotted.
        if vt_col == "ticker":
            wanted |= {s.ticker for s in symbols}
        frame = frame[frame[vt_col].astype(str).isin(wanted)]
    # Time filter — accept ``timestamp`` / ``ts`` / ``datetime``.
    ts_col = next(
        (c for c in ("timestamp", "ts", "datetime", "as_of") if c in frame.columns),
        None,
    )
    if ts_col:
        # Coerce defensively; some catalogs store epoch microseconds.
        coerced = pd.to_datetime(frame[ts_col], errors="coerce", utc=False)
        frame = frame.assign(_aqp_ts=coerced)
        frame = frame[(frame["_aqp_ts"] >= start_ts) & (frame["_aqp_ts"] <= end_ts)]
        frame = frame.drop(columns=["_aqp_ts"])
    return frame.reset_index(drop=True)


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
    """Run inference over an Iceberg slice (or DuckDB bars) and return signals.

    When ``iceberg_identifier`` is supplied we read the slice via
    :func:`aqp.data.iceberg_catalog.read_arrow` (AGENTS.md rule 3 — no
    raw PyIceberg in task code). Otherwise we fall back to the existing
    DuckDB bars path. This closes the documented gap where
    ``iceberg_identifier`` was echoed but unused.
    """
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

        source = "duckdb"
        if iceberg_identifier:
            emit(
                task_id,
                "loading",
                f"Reading Iceberg slice {iceberg_identifier}",
            )
            bars = _load_iceberg_slice(
                iceberg_identifier,
                symbols=parsed,
                start_ts=start_ts,
                end_ts=end_ts,
            )
            source = "iceberg"
        else:
            provider = DuckDBHistoryProvider()
            bars = provider.get_bars(parsed, start=start_ts, end=end_ts)
        if bars.empty:
            raise RuntimeError(
                f"No rows between {start_ts.date()} and {end_ts.date()} for {symbols}"
                f" (source={source})"
            )
        alpha = DeployedModelAlpha(deployment_id=deployment_id)
        emit(task_id, "running", f"Scoring {len(bars)} rows from {source}")
        signals = alpha.generate_signals(
            bars=bars, universe=parsed, context={"current_time": end_ts}
        )
        rows = _signals_to_rows(signals, last_n)
        result = {
            "deployment_id": deployment_id,
            "n_bars": int(len(bars)),
            "n_signals": int(len(signals)),
            "iceberg_identifier": iceberg_identifier,
            "source": source,
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
