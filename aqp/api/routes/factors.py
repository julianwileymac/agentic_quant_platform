"""Factor-evaluation API.

Three surfaces:

- ``POST /factors/evaluate`` — enqueues a Celery task that produces an
  Alphalens-style tear sheet and logs it to MLflow. Returns a
  ``TaskAccepted`` with a ``stream_url`` the UI can subscribe to.
- ``GET /factors/operators`` — lists the operator names registered with
  :mod:`aqp.data.expressions` so the Factor Workbench can render its
  reference palette.
- ``POST /factors/preview`` — evaluates a formula on a small universe and
  returns summary IC + the last rows so the UI can validate DSL formulas
  interactively before kicking off a full evaluation.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from aqp.api.schemas import TaskAccepted
from aqp.tasks.factor_tasks import evaluate_factor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/factors", tags=["factors"])


class FactorRequest(BaseModel):
    symbols: list[str] = Field(..., description="vt_symbols or ticker strings")
    start: str
    end: str
    factor_name: str = Field(default="mean_reversion_zscore")
    formula: str | None = Field(default=None, description="Optional expressions DSL formula")
    lookback: int = Field(default=20)
    n_quantiles: int = Field(default=5)
    horizons: list[int] = Field(default_factory=lambda: [1, 5, 10, 21])


class PreviewRequest(BaseModel):
    """Interactive preview request — small, fast, no MLflow side-effects."""

    symbols: list[str] = Field(..., description="Max ~10 symbols for snappy feedback")
    formula: str
    start: str | None = None
    end: str | None = None
    horizons: list[int] = Field(default_factory=lambda: [1, 5, 10])
    n_quantiles: int = Field(default=5, ge=2, le=20)
    rows: int = Field(default=50, ge=5, le=500)


class OperatorInfo(BaseModel):
    name: str
    category: str = "other"
    arity: int = 1
    description: str = ""


OPERATOR_DOCS: dict[str, tuple[str, int, str]] = {
    # Unary element-wise
    "Ref": ("unary", 2, "Lagged value: Ref(x, n) = x.shift(n)."),
    "Delta": ("unary", 2, "First difference over n bars."),
    "Abs": ("unary", 1, "Absolute value."),
    "Sign": ("unary", 1, "Sign of the series."),
    "Log": ("unary", 1, "Natural log (safely clipped)."),
    "Power": ("unary", 2, "Element-wise power."),
    "Rank": ("unary", 1, "Percentile rank within each timestamp group."),
    # Rolling aggregations
    "Mean": ("rolling", 2, "Rolling mean."),
    "Std": ("rolling", 2, "Rolling standard deviation."),
    "Var": ("rolling", 2, "Rolling variance."),
    "Skew": ("rolling", 2, "Rolling skew."),
    "Kurt": ("rolling", 2, "Rolling kurtosis."),
    "Sum": ("rolling", 2, "Rolling sum."),
    "Min": ("rolling", 2, "Rolling min."),
    "Max": ("rolling", 2, "Rolling max."),
    "Med": ("rolling", 2, "Rolling median."),
    "Mad": ("rolling", 2, "Rolling mean-absolute-deviation."),
    "Quantile": ("rolling", 3, "Rolling quantile."),
    "Count": ("rolling", 2, "Rolling count of truthy values."),
    "IdxMax": ("rolling", 2, "Index of rolling maximum."),
    "IdxMin": ("rolling", 2, "Index of rolling minimum."),
    "EMA": ("rolling", 2, "Exponential moving average."),
    "WMA": ("rolling", 2, "Weighted moving average."),
    "Slope": ("rolling", 2, "Rolling OLS slope."),
    "Rsquare": ("rolling", 2, "Rolling R² of OLS fit."),
    "Resi": ("rolling", 2, "Residual of last value vs OLS fit."),
    # Pairwise rolling
    "Corr": ("pairwise", 3, "Rolling correlation between two series."),
    "Cov": ("pairwise", 3, "Rolling covariance between two series."),
    # Comparison
    "Greater": ("compare", 2, "a > b -> 0/1."),
    "Less": ("compare", 2, "a < b -> 0/1."),
    "Gt": ("compare", 2, "Alias for Greater."),
    "Ge": ("compare", 2, "a >= b -> 0/1."),
    "Lt": ("compare", 2, "Alias for Less."),
    "Le": ("compare", 2, "a <= b -> 0/1."),
    "Eq": ("compare", 2, "a == b -> 0/1."),
    "Ne": ("compare", 2, "a != b -> 0/1."),
    # Logical
    "And": ("logical", 2, "Element-wise boolean AND."),
    "Or": ("logical", 2, "Element-wise boolean OR."),
    "Not": ("logical", 1, "Element-wise boolean NOT."),
    # Conditional
    "Mask": ("conditional", 3, "Replace series values where condition holds."),
    "If": ("conditional", 3, "Ternary: cond ? a : b."),
    # Arithmetic
    "Add": ("arithmetic", 2, "a + b."),
    "Sub": ("arithmetic", 2, "a - b."),
    "Mul": ("arithmetic", 2, "a * b."),
    "Div": ("arithmetic", 2, "a / b."),
}


@router.post("/evaluate", response_model=TaskAccepted)
def evaluate(req: FactorRequest) -> TaskAccepted:
    async_result = evaluate_factor.delay(
        symbols=req.symbols,
        start=req.start,
        end=req.end,
        factor_name=req.factor_name,
        formula=req.formula,
        lookback=req.lookback,
        n_quantiles=req.n_quantiles,
        horizons=tuple(req.horizons),
    )
    return TaskAccepted(
        task_id=async_result.id,
        stream_url=f"/chat/stream/{async_result.id}",
    )


@router.get("/operators", response_model=list[OperatorInfo])
def operators() -> list[OperatorInfo]:
    """Enumerate operators available to the expressions DSL."""
    from aqp.data.expressions import registered_operators

    out: list[OperatorInfo] = []
    for name in registered_operators():
        category, arity, desc = OPERATOR_DOCS.get(
            name, ("other", 1, "No description available.")
        )
        out.append(
            OperatorInfo(
                name=name, category=category, arity=arity, description=desc
            )
        )
    return out


@router.post("/preview")
def preview(req: PreviewRequest) -> dict[str, Any]:
    """Evaluate ``req.formula`` on a small bar slice and return a sample + IC.

    Designed to power the Factor Workbench "Formula Lab" preview — we don't
    hit Celery, we don't log to MLflow, and we cap the response to the last
    ``req.rows`` rows for fast round-trips.
    """
    import datetime as _dt

    from aqp.core.types import DataNormalizationMode, Symbol
    from aqp.data.duckdb_engine import DuckDBHistoryProvider
    from aqp.data.expressions import Expression, ExpressionError
    from aqp.data.factors import (
        align_factor_and_returns,
        compute_forward_returns,
        factor_information_coefficient,
        ic_summary,
    )

    try:
        expr = Expression(req.formula)
    except ExpressionError as exc:
        raise HTTPException(status_code=400, detail=f"formula error: {exc}") from exc

    symbols = [Symbol.parse(s) if "." in s else Symbol(ticker=s) for s in req.symbols]
    start_dt = _parse_ts(req.start, default=_dt.datetime(2020, 1, 1))
    end_dt = _parse_ts(req.end, default=_dt.datetime.utcnow())

    provider = DuckDBHistoryProvider()
    bars = provider.get_bars_normalized(
        symbols,
        start_dt,
        end_dt,
        interval="1d",
        normalization=DataNormalizationMode.ADJUSTED,
    )
    if bars is None or bars.empty:
        return {
            "formula": req.formula,
            "rows": [],
            "summary": {},
            "message": "No bars returned for this universe + window.",
        }

    # Evaluate per-symbol and build a long-format result.
    frames: list[pd.DataFrame] = []
    for vt, sub in bars.sort_values("timestamp").groupby("vt_symbol", sort=False):
        try:
            values = expr(sub)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"formula evaluation failed for {vt}: {exc}",
            ) from exc
        if isinstance(values, (int, float)):
            values = pd.Series([values] * len(sub), index=sub.index)
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": pd.to_datetime(sub["timestamp"]).values,
                    "vt_symbol": vt,
                    "factor": values.values,
                    "close": sub["close"].values,
                }
            )
        )
    long = pd.concat(frames, ignore_index=True)
    long = long.dropna(subset=["factor"])

    try:
        fwd = compute_forward_returns(bars, periods=tuple(req.horizons))
        aligned = align_factor_and_returns(long, fwd, factor_column="factor")
        ic_ts = factor_information_coefficient(aligned, method="spearman")
        ic = ic_summary(ic_ts) if not ic_ts.empty else {}
        summary = {
            k: {kk: float(vv) for kk, vv in v.items()} if isinstance(v, dict) else v
            for k, v in ic.items()
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("ic summary failed in preview: %s", exc, exc_info=True)
        summary = {"error": str(exc)}

    sample = long.tail(req.rows).copy()
    sample["timestamp"] = sample["timestamp"].astype(str)
    return {
        "formula": req.formula,
        "rows": sample.to_dict(orient="records"),
        "summary": summary,
        "n_rows": int(len(long)),
        "n_symbols": int(long["vt_symbol"].nunique()),
    }


def _parse_ts(text: str | None, *, default):
    if not text:
        return default
    try:
        import datetime as _dt

        return _dt.datetime.fromisoformat(text)
    except ValueError:
        return default
