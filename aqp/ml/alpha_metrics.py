"""Combined ML + trading metric helpers for ``AlphaBacktestExperiment``.

The standard ``Experiment`` evaluates predictions in isolation (IC, MAE,
RMSE). The ``AlphaBacktestExperiment`` orchestrator additionally drives a
backtest where those predictions feed an alpha, so we need a small set of
helpers that:

1. Compute ML metrics from a (prediction, label) pair (``compute_alpha_metrics``).
2. Compute attribution metrics from (predictions, fills) — does conviction
   translate to PnL? (``compute_attribution``).
3. Roll the two metric families into a single weighted score for sweeps
   (``combined_score``).

All helpers are pure and import-light so they can run inside a Celery
worker without dragging in optional ML deps.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def compute_alpha_metrics(
    predictions: pd.Series,
    labels: pd.Series,
    *,
    horizons: tuple[int, ...] = (1, 5, 10, 20),
) -> dict[str, float]:
    """ML-side metrics: IC, MAE, RMSE, hit-rate, decay-by-horizon.

    Both ``predictions`` and ``labels`` are coerced to ``float`` Series and
    aligned on their joint index. Missing values are dropped before
    metrics are computed.
    """
    pred = pd.Series(predictions, dtype=float, copy=True).rename("pred")
    lab = pd.Series(labels, dtype=float, copy=True).rename("label")
    joined = pd.concat([pred, lab], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
    metrics: dict[str, float] = {
        "n_predictions": int(len(pred)),
        "n_labels_aligned": int(len(joined)),
    }
    if joined.empty:
        return metrics

    err = joined["pred"] - joined["label"]
    metrics["rmse"] = _safe_float(np.sqrt(np.mean(np.square(err))))
    metrics["mae"] = _safe_float(np.mean(np.abs(err)))
    metrics["bias"] = _safe_float(err.mean())
    metrics["ic_pearson"] = _safe_float(
        joined["pred"].corr(joined["label"], method="pearson")
    )
    metrics["ic_spearman"] = _safe_float(
        joined["pred"].corr(joined["label"], method="spearman")
    )
    metrics["hit_rate"] = _safe_float(
        (np.sign(joined["pred"]) == np.sign(joined["label"])).mean()
    )
    # Information ratio of period predictions against labels (per-period IC).
    if len(joined) > 5:
        try:
            chunked = np.array_split(joined, min(5, len(joined) // 5))
            per_chunk_ic = [
                _safe_float(c["pred"].corr(c["label"], method="spearman"))
                for c in chunked
                if len(c) > 1
            ]
            if per_chunk_ic:
                metrics["ic_mean"] = _safe_float(np.mean(per_chunk_ic))
                metrics["ic_std"] = _safe_float(np.std(per_chunk_ic))
                metrics["icir"] = _safe_float(
                    metrics["ic_mean"] / metrics["ic_std"]
                    if metrics["ic_std"] > 0
                    else 0.0
                )
        except Exception:
            logger.debug("ICIR estimation skipped", exc_info=True)

    # Decay-by-horizon: how the IC evolves when labels are shifted forward.
    for h in horizons:
        try:
            shifted = joined["label"].shift(-int(h))
            ic = joined["pred"].corr(shifted, method="spearman")
            metrics[f"ic_h{int(h)}"] = _safe_float(ic)
        except Exception:
            continue
    return metrics


def compute_trading_metrics(
    summary: Mapping[str, Any] | None,
    equity_curve: pd.Series | None = None,
) -> dict[str, float]:
    """Extract a normalized set of trading metrics from a backtest summary.

    ``summary`` is the JSON dict returned from
    :func:`aqp.backtest.runner.run_backtest_from_config` (i.e. what we
    persist to ``backtest_runs.metrics``). We pull a stable subset and
    derive a few extras (Calmar, turnover-adjusted Sharpe) when possible.
    """
    summary = dict(summary or {})
    out: dict[str, float] = {}
    for key in (
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "total_return",
        "annualized_return",
        "annualized_volatility",
        "final_equity",
        "n_trades",
        "win_rate",
        "profit_factor",
        "avg_win",
        "avg_loss",
        "turnover",
    ):
        if key in summary and summary[key] is not None:
            out[key] = _safe_float(summary[key])

    sharpe = out.get("sharpe", 0.0)
    turnover = out.get("turnover", 0.0)
    if sharpe and turnover > 0:
        # Penalize turnover linearly (one-percent turnover -> one-percent shave
        # off Sharpe). Heuristic, kept small to avoid swamping the Sharpe.
        out["turnover_adj_sharpe"] = _safe_float(sharpe * (1.0 - min(turnover, 0.95) * 0.1))

    if equity_curve is not None and len(equity_curve) > 1:
        try:
            ec = pd.Series(equity_curve, dtype=float).dropna()
            if not ec.empty:
                returns = ec.pct_change().dropna()
                if not returns.empty:
                    out.setdefault("annualized_volatility", _safe_float(returns.std() * np.sqrt(252)))
                    if "annualized_return" not in out and len(ec) > 1:
                        years = max(len(ec) / 252.0, 1e-6)
                        total = ec.iloc[-1] / max(ec.iloc[0], 1e-9) - 1.0
                        out["annualized_return"] = _safe_float((1 + total) ** (1 / years) - 1)
        except Exception:
            logger.debug("equity-curve derived metrics skipped", exc_info=True)
    return out


def compute_attribution(
    predictions: pd.Series | None,
    timeline: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """High-conviction-vs-PnL attribution.

    ``timeline`` is the backtest result timeline (the
    ``metrics["timeline"]`` blob persisted on ``BacktestRun``); we pull the
    fills/trades and join against the per-bar predictions to ask: did the
    top-decile predictions actually translate to positive PnL?
    """
    out: dict[str, Any] = {"available": False}
    if predictions is None or timeline is None:
        return out
    try:
        pred = pd.Series(predictions, dtype=float).dropna()
        trades_raw = timeline.get("trades") if isinstance(timeline, Mapping) else None
        if not trades_raw:
            return out
        trades = pd.DataFrame(trades_raw)
        if trades.empty or "pnl" not in trades.columns:
            return out

        out["n_trades"] = int(len(trades))
        if "vt_symbol" in trades.columns and "ts" in trades.columns:
            # Sort and bucket by prediction-quantile if predictions are indexed
            # by (ts, vt_symbol). Best-effort: keep this resilient to flat
            # series or single-symbol predictions.
            try:
                trades["pnl"] = trades["pnl"].astype(float)
                quantile = pred.quantile([0.1, 0.5, 0.9]).to_dict()
                top_threshold = _safe_float(quantile.get(0.9, pred.max()))
                bottom_threshold = _safe_float(quantile.get(0.1, pred.min()))
                out["top_decile_threshold"] = top_threshold
                out["bottom_decile_threshold"] = bottom_threshold
                # Approximate decile assignment by per-trade timestamp lookup
                if isinstance(pred.index, pd.MultiIndex):
                    decile_pnl_map: dict[str, float] = {"top": 0.0, "bottom": 0.0, "middle": 0.0}
                    for _, trade in trades.iterrows():
                        try:
                            key = (pd.Timestamp(trade["ts"]), str(trade["vt_symbol"]))
                            score = float(pred.loc[key]) if key in pred.index else None
                        except Exception:
                            score = None
                        bucket = "middle"
                        if score is not None:
                            if score >= top_threshold:
                                bucket = "top"
                            elif score <= bottom_threshold:
                                bucket = "bottom"
                        decile_pnl_map[bucket] += float(trade["pnl"])
                    out["pnl_by_decile"] = decile_pnl_map
            except Exception:
                logger.debug("trade decile attribution skipped", exc_info=True)
        out["total_pnl"] = _safe_float(trades["pnl"].astype(float).sum())
        out["available"] = True
    except Exception:
        logger.debug("attribution computation skipped", exc_info=True)
    return out


_DEFAULT_WEIGHTS = {
    "sharpe": 0.45,
    "icir": 0.20,
    "ic_spearman": 0.15,
    "hit_rate": 0.10,
    "calmar": 0.10,
}


def combined_score(
    ml_metrics: Mapping[str, Any] | None,
    trading_metrics: Mapping[str, Any] | None,
    weights: Mapping[str, float] | None = None,
) -> float:
    """Roll ML + trading metrics into a single scalar suitable for sweeps.

    Defaults weight Sharpe heavily but keep IC/IR/hit-rate as inputs so a
    high-IC model that fails to translate to trading PnL is penalized.
    """
    w = dict(_DEFAULT_WEIGHTS)
    if weights:
        w.update({k: float(v) for k, v in weights.items()})
    ml = dict(ml_metrics or {})
    tr = dict(trading_metrics or {})
    score = 0.0
    for key, weight in w.items():
        value = tr.get(key, ml.get(key))
        if value is None:
            continue
        score += weight * _safe_float(value)
    return _safe_float(score)


__all__ = [
    "combined_score",
    "compute_alpha_metrics",
    "compute_attribution",
    "compute_trading_metrics",
]
