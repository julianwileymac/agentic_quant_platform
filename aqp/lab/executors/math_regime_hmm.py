"""``math.regime_hmm`` — Hidden Markov regime detection.

When ``hmmlearn`` is installed we use ``GaussianHMM`` to fit a
classic latent-state model on the upstream return series. When it
isn't available, we degrade gracefully to a deterministic two-state
labeller backed by the existing :func:`aqp.strategies.regime_detection.slow_regime`
helper. The fallback path keeps the executor importable on any
machine that has the core AQP stack but skips the optional ML
extras.

Params:

- ``n_states`` (int, default 3) — number of latent regimes (HMM
  path only).
- ``feature_column`` (str, default ``"close"``).
- ``returns_lookback`` (int, default 1) — diff-window for the
  return series fed to the HMM.
- ``backend`` (Literal['auto','hmmlearn','heuristic'], default
  'auto') — force a path for testing.

Emits a SIGNAL frame with columns ``[regime, prob_<state>]`` keyed
by the upstream's timestamp index.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import (
    base_locator,
    resolve_upstream_frame,
    stash_arrow_output,
)
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    n_states = int(params.get("n_states") or 3)
    feature_column = str(params.get("feature_column") or "close")
    returns_lookback = int(params.get("returns_lookback") or 1)
    backend = str(params.get("backend") or "auto").lower()
    if backend not in {"auto", "hmmlearn", "heuristic"}:
        return NodeResult(
            status="error",
            error=f"math.regime_hmm: unknown backend {backend!r}",
            log_label="math.regime_hmm:bad_backend",
        )

    df = resolve_upstream_frame(ctx)
    if df is None or feature_column not in df.columns:
        return NodeResult(
            status="error",
            error=(
                f"math.regime_hmm: upstream frame missing feature column "
                f"{feature_column!r}"
            ),
            log_label="math.regime_hmm:no_feature",
        )
    if len(df) < max(20, n_states * 5):
        return NodeResult(
            status="error",
            error=(
                f"math.regime_hmm: need at least {max(20, n_states * 5)} rows "
                f"for n_states={n_states}; got {len(df)}"
            ),
            log_label="math.regime_hmm:short_series",
        )

    series = df[feature_column].astype(float)
    returns = series.pct_change(returns_lookback).fillna(0.0).to_numpy().reshape(-1, 1)

    use_hmmlearn = backend in {"auto", "hmmlearn"}
    if use_hmmlearn:
        regimes_df = _fit_hmm(returns, n_states=n_states)
        if regimes_df is not None:
            regimes_df.insert(0, "datetime", series.index)
            stash_arrow_output(ctx, node.id, regimes_df)
            return NodeResult(
                status="done",
                output_locator={
                    **base_locator(node.id, regimes_df, kind="regime_hmm"),
                    "backend": "hmmlearn",
                    "n_states": n_states,
                    "feature_column": feature_column,
                },
                metrics={
                    "rows": int(len(regimes_df)),
                    "unique_regimes": int(regimes_df["regime"].nunique()),
                    "backend": "hmmlearn",
                },
                log_label=f"math.regime_hmm:hmmlearn:k={n_states}",
            )

    # Heuristic fallback — bucket the returns by rolling z-score so
    # the executor still produces a usable signal without hmmlearn.
    return _heuristic_fallback(node, ctx, series, returns, n_states, feature_column)


def _fit_hmm(returns: np.ndarray, *, n_states: int) -> pd.DataFrame | None:
    try:
        from hmmlearn.hmm import GaussianHMM  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    try:
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
        )
        model.fit(returns)
        states = model.predict(returns)
        log_post = model.predict_proba(returns)
    except Exception as exc:  # noqa: BLE001
        logger.debug("hmmlearn fit failed: %s", exc, exc_info=True)
        return None
    frame = pd.DataFrame({"regime": states})
    for k in range(log_post.shape[1]):
        frame[f"prob_{k}"] = log_post[:, k]
    return frame


def _heuristic_fallback(
    node: Any,
    ctx: NodeContext,
    series: pd.Series,
    returns: np.ndarray,
    n_states: int,
    feature_column: str,
) -> NodeResult:
    """Bucket returns into quantile-based regimes when hmmlearn is missing."""
    flat_returns = returns.ravel()
    quantiles = np.quantile(flat_returns, np.linspace(0, 1, n_states + 1)[1:-1])
    states = np.digitize(flat_returns, quantiles)
    frame = pd.DataFrame({"regime": states.astype(int)})
    for k in range(n_states):
        frame[f"prob_{k}"] = (states == k).astype(float)
    frame.insert(0, "datetime", series.index)
    stash_arrow_output(ctx, node.id, frame)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, frame, kind="regime_hmm"),
            "backend": "heuristic",
            "n_states": n_states,
            "feature_column": feature_column,
        },
        metrics={
            "rows": int(len(frame)),
            "unique_regimes": int(frame["regime"].nunique()),
            "backend": "heuristic",
        },
        log_label=f"math.regime_hmm:heuristic:k={n_states}",
    )


__all__ = ["execute"]
