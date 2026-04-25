"""Celery task for Alphalens-style factor evaluation.

The payload is a serialisable request: symbol list, date range, and
either a named built-in factor (``"mean_reversion_zscore"``,
``"momentum_rank"``) or a raw :mod:`aqp.data.expressions` formula.

The task computes a :class:`aqp.data.factors.FactorReport`, dumps its
scalar summary back over the progress bus, and logs the full report to
MLflow via :func:`aqp.mlops.mlflow_client.log_factor_run`.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from aqp.tasks._progress import emit, emit_done, emit_error
from aqp.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="aqp.tasks.factor_tasks.evaluate_factor")
def evaluate_factor(
    self,
    symbols: list[str],
    start: str,
    end: str,
    factor_name: str = "mean_reversion_zscore",
    formula: str | None = None,
    lookback: int = 20,
    n_quantiles: int = 5,
    horizons: tuple[int, ...] = (1, 5, 10, 21),
) -> dict[str, Any]:
    """Evaluate a factor against the Parquet lake."""
    task_id = self.request.id or "local"
    emit(task_id, "start", f"Evaluating factor {factor_name!r} on {len(symbols)} symbols…")
    try:
        from aqp.core.types import Symbol
        from aqp.data.duckdb_engine import DuckDBHistoryProvider
        from aqp.data.factors import evaluate_factor as _eval
        from aqp.mlops.mlflow_client import log_factor_run

        provider = DuckDBHistoryProvider()
        syms = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in symbols]
        bars = provider.get_bars(
            syms,
            pd.Timestamp(start).to_pydatetime(),
            pd.Timestamp(end).to_pydatetime(),
        )
        if bars.empty:
            raise RuntimeError("No bars found for the requested universe / window")

        factor_df = _compute_factor(bars, name=factor_name, formula=formula, lookback=lookback)
        report = _eval(
            factor=factor_df,
            prices=bars,
            factor_name=factor_name,
            periods=tuple(horizons),
            n_quantiles=n_quantiles,
        )
        summary = report.to_dict()
        mlflow_run_id = log_factor_run(
            factor_name=factor_name,
            ic_stats=report.ic_stats,
            cumulative_returns=report.cumulative_returns,
            turnover_mean=float(report.turnover.mean()) if not report.turnover.empty else 0.0,
        )
        summary["mlflow_run_id"] = mlflow_run_id
        emit_done(task_id, summary)
        return summary
    except Exception as exc:  # pragma: no cover
        logger.exception("evaluate_factor failed")
        emit_error(task_id, str(exc))
        raise


def _compute_factor(
    bars: pd.DataFrame,
    name: str,
    formula: str | None,
    lookback: int = 20,
) -> pd.DataFrame:
    """Build a long-format ``(timestamp, vt_symbol, factor)`` frame."""
    if formula:
        from aqp.data.expressions import compute

        df = compute(formula, bars)
        df = df.rename(columns={df.columns[-1]: "factor"})
        return df[["timestamp", "vt_symbol", "factor"]]
    if name == "mean_reversion_zscore":
        records = []
        for _vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            sub = sub.sort_values("timestamp")
            close = sub["close"]
            mean = close.rolling(lookback).mean()
            std = close.rolling(lookback).std().replace(0, float("nan"))
            z = (close - mean) / std
            df = pd.DataFrame(
                {
                    "timestamp": sub["timestamp"],
                    "vt_symbol": sub["vt_symbol"],
                    "factor": -z,  # mean-reversion ⇒ sign-flipped z
                }
            )
            records.append(df)
        return pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    if name == "momentum_rank":
        records = []
        for _vt_symbol, sub in bars.groupby("vt_symbol", sort=False):
            sub = sub.sort_values("timestamp")
            ret = sub["close"].pct_change(lookback)
            records.append(
                pd.DataFrame(
                    {
                        "timestamp": sub["timestamp"],
                        "vt_symbol": sub["vt_symbol"],
                        "factor": ret,
                    }
                )
            )
        return pd.concat(records, ignore_index=True) if records else pd.DataFrame()
    raise ValueError(f"unknown factor {name!r} (and no formula provided)")
