"""Alphalens-style factor-evaluation flow.

Thin facade over :mod:`aqp.data.factors` so the lab UI's Factor tab
deep-links into a registered analysis flow rather than calling the
factor-evaluation endpoint directly. The heavy lifting still happens
in the original module.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


class FactorEvalParams(FlowParams):
    factor_column: str = "factor"
    price_column: str = "close"
    timestamp_column: str = "timestamp"
    symbol_column: str = "vt_symbol"
    periods: list[int] = Field(default_factory=lambda: [1, 5, 10, 21])
    n_quantiles: int = Field(default=5, ge=2, le=20)
    factor_name: str = "factor"


@register_analysis_flow(
    name="factors.evaluate",
    namespace="factors",
    label="Factor evaluation (Alphalens-style)",
    description=(
        "Compute IC + quantile returns + spread + turnover for a "
        "long-format factor frame. Wraps aqp.data.factors.evaluate_factor."
    ),
    params_model=FactorEvalParams,
    tags=("factor", "alphalens"),
)
def factor_evaluate_flow(
    df: pd.DataFrame, params: FactorEvalParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.factors import evaluate_factor

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    needed = {
        params.factor_column,
        params.price_column,
        params.timestamp_column,
        params.symbol_column,
    }
    if not needed.issubset(df.columns):
        return FlowResult(
            flow="factors.evaluate",
            error=f"missing required columns; need {sorted(needed)}",
        )
    factor = df[
        [params.timestamp_column, params.symbol_column, params.factor_column]
    ].rename(
        columns={
            params.timestamp_column: "timestamp",
            params.symbol_column: "vt_symbol",
            params.factor_column: "factor",
        }
    )
    prices = df[
        [params.timestamp_column, params.symbol_column, params.price_column]
    ].rename(
        columns={
            params.timestamp_column: "timestamp",
            params.symbol_column: "vt_symbol",
            params.price_column: "close",
        }
    )
    report = evaluate_factor(
        factor=factor,
        prices=prices,
        factor_name=params.factor_name,
        factor_column="factor",
        periods=tuple(int(p) for p in params.periods),
        n_quantiles=int(params.n_quantiles),
        price_column="close",
    )

    ic_stats = report.ic_stats or {}
    metrics: dict[str, Any] = {
        "factor_name": params.factor_name,
        "periods": list(params.periods),
        "n_quantiles": int(params.n_quantiles),
    }
    for horizon, stats in ic_stats.items():
        metrics[f"ic_mean_{horizon}"] = float(stats.get("ic_mean", 0.0))
        metrics[f"ic_t_stat_{horizon}"] = float(stats.get("t_stat", 0.0))
        metrics[f"ic_ir_{horizon}"] = float(stats.get("ir", 0.0))
        metrics[f"ic_hit_rate_{horizon}"] = float(stats.get("hit_rate", 0.0))
    metrics["turnover_mean"] = (
        float(report.turnover.mean()) if not report.turnover.empty else 0.0
    )

    quantile_rows: list[dict[str, Any]] = []
    if not report.cumulative_returns.empty:
        cum = report.cumulative_returns.tail(500).reset_index()
        for record in cum.to_dict(orient="records"):
            quantile_rows.append(
                {k: (float(v) if isinstance(v, (int, float, np.floating)) else str(v)) for k, v in record.items()}
            )

    return FlowResult(
        flow="factors.evaluate",
        metrics=metrics,
        rows=quantile_rows,
        artifacts={"summary": report.to_dict()},
        arrow_table=coerce_arrow(quantile_rows),
    )


_ = pd


__all__ = ["FactorEvalParams", "factor_evaluate_flow"]
