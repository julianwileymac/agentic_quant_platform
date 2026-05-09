"""Microstructure + realised-volatility flows.

Thin facades over :mod:`aqp.data.microstructure` and
:mod:`aqp.data.realised_volatility` so the lab UI gets uniform forms.
No code is duplicated — every helper points at the existing
implementation.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Realised volatility — five-estimator panel
# ---------------------------------------------------------------------------


class RealisedVolParams(FlowParams):
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    period: int = Field(default=20, ge=2, le=2000)
    annualize: int | None = Field(default=252, ge=1, le=525_600)
    estimators: list[Literal[
        "close_to_close",
        "parkinson",
        "garman_klass",
        "rogers_satchell",
        "yang_zhang",
    ]] = Field(default_factory=lambda: ["close_to_close", "parkinson", "garman_klass", "yang_zhang"])
    max_rows: int = Field(default=500, ge=1, le=10_000)


@register_analysis_flow(
    name="microstructure.realised_volatility",
    namespace="microstructure",
    label="Realised volatility (OHLC)",
    description=(
        "Compute the close-to-close / Parkinson / Garman-Klass / "
        "Rogers-Satchell / Yang-Zhang estimators side-by-side."
    ),
    params_model=RealisedVolParams,
    tags=("microstructure", "volatility"),
)
def realised_volatility_flow(
    df: pd.DataFrame, params: RealisedVolParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.realised_volatility import (
        close_to_close,
        garman_klass,
        parkinson,
        rogers_satchell,
        yang_zhang,
    )

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    needed = {params.open_column, params.high_column, params.low_column, params.close_column}
    if not needed.issubset(df.columns):
        return FlowResult(
            flow="microstructure.realised_volatility",
            error=f"missing OHLC columns; need {sorted(needed)}",
        )
    open_, high, low, close = (
        df[params.open_column],
        df[params.high_column],
        df[params.low_column],
        df[params.close_column],
    )
    out: dict[str, pd.Series] = {}
    if "close_to_close" in params.estimators:
        out["close_to_close"] = close_to_close(close, params.period, params.annualize)
    if "parkinson" in params.estimators:
        out["parkinson"] = parkinson(high, low, params.period, params.annualize)
    if "garman_klass" in params.estimators:
        out["garman_klass"] = garman_klass(open_, high, low, close, params.period, params.annualize)
    if "rogers_satchell" in params.estimators:
        out["rogers_satchell"] = rogers_satchell(open_, high, low, close, params.period, params.annualize)
    if "yang_zhang" in params.estimators:
        out["yang_zhang"] = yang_zhang(open_, high, low, close, params.period, params.annualize)
    panel = pd.DataFrame(out).dropna(how="all")
    if panel.empty:
        return FlowResult(
            flow="microstructure.realised_volatility",
            metrics={"n": int(len(df))},
            error="all-NaN output",
        )
    rows = panel.tail(int(params.max_rows)).reset_index().to_dict(orient="records")
    metrics: dict[str, Any] = {
        "n_rows": int(len(panel)),
        "period": int(params.period),
        "annualize": int(params.annualize) if params.annualize else None,
    }
    for col in panel.columns:
        last = panel[col].dropna()
        if not last.empty:
            metrics[f"{col}_last"] = float(last.iloc[-1])
            metrics[f"{col}_mean"] = float(last.mean())
    return FlowResult(
        flow="microstructure.realised_volatility",
        metrics=metrics,
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Order-book imbalance
# ---------------------------------------------------------------------------


class OrderBookImbalanceParams(FlowParams):
    bid_qty_column: str = "bid_qty"
    ask_qty_column: str = "ask_qty"
    max_rows: int = Field(default=500, ge=1, le=10_000)


@register_analysis_flow(
    name="microstructure.order_book_imbalance",
    namespace="microstructure",
    label="Order-book imbalance",
    description="(bid_qty - ask_qty) / (bid_qty + ask_qty) on the top of book.",
    params_model=OrderBookImbalanceParams,
    tags=("microstructure", "order_book"),
)
def obi_flow(
    df: pd.DataFrame, params: OrderBookImbalanceParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.microstructure import order_book_imbalance

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if params.bid_qty_column not in df.columns or params.ask_qty_column not in df.columns:
        return FlowResult(
            flow="microstructure.order_book_imbalance",
            error="bid/ask qty columns not found",
        )
    series = order_book_imbalance(df[params.bid_qty_column], df[params.ask_qty_column])
    series = series.dropna() if isinstance(series, pd.Series) else pd.Series(series).dropna()
    rows = series.tail(int(params.max_rows)).reset_index().rename(columns={0: "obi"}).to_dict(orient="records")
    return FlowResult(
        flow="microstructure.order_book_imbalance",
        metrics={
            "n": int(len(series)),
            "mean": float(series.mean()) if len(series) else 0.0,
            "std": float(series.std()) if len(series) > 1 else 0.0,
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# VPIN
# ---------------------------------------------------------------------------


class VPINParams(FlowParams):
    buy_volume_column: str = "buy_volume"
    sell_volume_column: str = "sell_volume"
    n_buckets: int = Field(default=50, ge=2, le=2000)
    max_rows: int = Field(default=500, ge=1, le=10_000)


@register_analysis_flow(
    name="microstructure.vpin",
    namespace="microstructure",
    label="VPIN",
    description=(
        "Volume-synchronized probability of informed trading. "
        "Wraps aqp.data.microstructure.vpin."
    ),
    params_model=VPINParams,
    tags=("microstructure", "vpin"),
)
def vpin_flow(
    df: pd.DataFrame, params: VPINParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.microstructure import vpin

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if (
        params.buy_volume_column not in df.columns
        or params.sell_volume_column not in df.columns
    ):
        return FlowResult(
            flow="microstructure.vpin",
            error="buy/sell volume columns not found",
        )
    series = vpin(
        df[params.buy_volume_column],
        df[params.sell_volume_column],
        n_buckets=int(params.n_buckets),
    )
    series = series.dropna() if isinstance(series, pd.Series) else pd.Series(series).dropna()
    rows = (
        series.tail(int(params.max_rows))
        .reset_index()
        .rename(columns={0: "vpin"})
        .to_dict(orient="records")
    )
    return FlowResult(
        flow="microstructure.vpin",
        metrics={
            "n": int(len(series)),
            "mean": float(series.mean()) if len(series) else 0.0,
            "n_buckets": int(params.n_buckets),
        },
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


_ = np


__all__ = [
    "OrderBookImbalanceParams",
    "RealisedVolParams",
    "VPINParams",
    "obi_flow",
    "realised_volatility_flow",
    "vpin_flow",
]
