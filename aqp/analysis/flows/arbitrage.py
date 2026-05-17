"""Phase 4 arbitrage analysis flows.

Wraps :mod:`aqp.math.arbitrage` so the AnalysisRuntime can:

* Find cointegrated baskets across a universe (Johansen test)
* Emit pair-trading signals over a time series (rolling z-score + half-life)
* Monitor A/H share basis (cross-market arbitrage)
* Monitor ADR <-> underlying basis (cross-market arbitrage)
"""
from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from aqp.analysis.base import FlowContext, FlowParams, FlowResult
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# arbitrage.johansen_basket
# ---------------------------------------------------------------------------


class JohansenBasketParams(FlowParams):
    """Parameters for ``arbitrage.johansen_basket``."""

    columns: list[str] = Field(
        description="Column names in the dataset to test for joint cointegration."
    )
    deterministic: str = Field(
        default="constant",
        description="Trend specification: 'constant' | 'trend' | 'none'.",
    )
    k_ar_diff: int = Field(default=1, ge=0, le=10)


@register_analysis_flow(
    name="arbitrage.johansen_basket",
    namespace="arbitrage",
    label="Johansen cointegration test",
    description=(
        "Multivariate cointegration test across a basket of >=2 series. "
        "Returns the cointegration rank + trace + max-eigenvalue stats "
        "with 95%/99% critical values + the cointegrating vectors."
    ),
    params_model=JohansenBasketParams,
    requires_dataset=True,
    tags=("arbitrage", "cointegration", "johansen"),
    optional_dependencies=("statsmodels",),
)
def johansen_basket_flow(
    df: Any, params: JohansenBasketParams, ctx: FlowContext
) -> FlowResult:
    from aqp.math.arbitrage import johansen_test

    missing = [c for c in params.columns if c not in df.columns]
    if missing:
        return FlowResult(
            flow="arbitrage.johansen_basket",
            error=f"missing columns: {missing}",
        )
    subset = df[params.columns].dropna()
    result = johansen_test(
        subset,
        deterministic=params.deterministic,
        k_ar_diff=params.k_ar_diff,
    )
    rows = [
        {
            "rank_under_test": i,
            "trace_stat": result.trace_stat[i] if i < len(result.trace_stat) else None,
            "max_eigen_stat": (
                result.max_eigen_stat[i]
                if i < len(result.max_eigen_stat)
                else None
            ),
            "crit_trace_95": (
                result.crit_trace_95[i] if i < len(result.crit_trace_95) else None
            ),
            "crit_max_eigen_95": (
                result.crit_max_eigen_95[i]
                if i < len(result.crit_max_eigen_95)
                else None
            ),
            "rejects_at_95": (
                result.trace_stat[i] > result.crit_trace_95[i]
                if i < len(result.trace_stat)
                else None
            ),
        }
        for i in range(len(result.trace_stat))
    ]
    return FlowResult(
        flow="arbitrage.johansen_basket",
        metrics={
            "rank": result.rank,
            "is_cointegrated_95": result.is_cointegrated_95,
            "is_cointegrated_99": result.is_cointegrated_99,
            "n_series": result.n_series,
            "deterministic": result.deterministic,
        },
        rows=rows,
        artifacts={
            "cointegrating_vectors": result.cointegrating_vectors,
            "eigenvalues": result.eig,
        },
        error=result.error,
    )


# ---------------------------------------------------------------------------
# arbitrage.pair_signal
# ---------------------------------------------------------------------------


class PairSignalParams(FlowParams):
    """Parameters for ``arbitrage.pair_signal``."""

    spread_column: str = Field(description="Column carrying the (a_price - hedge * b_price) spread.")
    entry_threshold: float = Field(default=2.0, gt=0.0)
    exit_threshold: float = Field(default=0.5, ge=0.0)
    zscore_window: int = Field(default=60, ge=10, le=2000)
    half_life_min: float | None = Field(default=None)


@register_analysis_flow(
    name="arbitrage.pair_signal",
    namespace="arbitrage",
    label="Pair-trading entry / exit signal",
    description=(
        "Rolling z-score + Ornstein-Uhlenbeck half-life signal for "
        "pair trading. Returns the latest signal kind (ENTRY_LONG_SPREAD / "
        "ENTRY_SHORT_SPREAD / EXIT / HOLD), the current z-score, and the "
        "estimated half-life."
    ),
    params_model=PairSignalParams,
    requires_dataset=True,
    tags=("arbitrage", "pair_trading", "zscore"),
)
def pair_signal_flow(
    df: Any, params: PairSignalParams, ctx: FlowContext
) -> FlowResult:
    from aqp.math.arbitrage import pair_signal

    if params.spread_column not in df.columns:
        return FlowResult(
            flow="arbitrage.pair_signal",
            error=f"missing column: {params.spread_column}",
        )
    spread = df[params.spread_column].dropna()
    signal = pair_signal(
        spread,
        entry_threshold=params.entry_threshold,
        exit_threshold=params.exit_threshold,
        window=params.zscore_window,
        half_life_min=params.half_life_min,
    )
    return FlowResult(
        flow="arbitrage.pair_signal",
        metrics={
            "signal_kind": str(signal.kind),
            "zscore": float(signal.zscore),
            "spread": float(signal.spread),
            "half_life": signal.half_life if signal.half_life is not None else None,
            "reason": signal.reason,
        },
        rows=[
            {
                "signal_kind": str(signal.kind),
                "zscore": float(signal.zscore),
                "spread": float(signal.spread),
                "half_life": signal.half_life
                if signal.half_life is not None
                else None,
            }
        ],
    )


# ---------------------------------------------------------------------------
# arbitrage.ah_share_basis
# ---------------------------------------------------------------------------


class AHShareBasisParams(FlowParams):
    """Parameters for ``arbitrage.ah_share_basis``."""

    a_price_column: str = Field(description="Column with A-share price in CNY.")
    h_price_column: str = Field(description="Column with H-share price in HKD.")
    fx_column: str | None = Field(
        default=None,
        description="Column with CNYHKD FX rate. If None, ``fx_rate`` is used.",
    )
    fx_rate: float = Field(
        default=0.917,
        gt=0.0,
        description="Static CNY per HKD when fx_column is not provided.",
    )
    conversion_ratio: float = Field(default=1.0, gt=0.0)
    transaction_cost_bps: float = Field(default=20.0, ge=0.0)
    threshold_bps: float = Field(default=100.0, ge=0.0)
    preview_rows: int = Field(default=200, ge=1, le=5000)


@register_analysis_flow(
    name="arbitrage.ah_share_basis",
    namespace="arbitrage",
    label="A-share <-> H-share basis monitor",
    description=(
        "Cross-market basis between mainland China A-shares (CNY) and "
        "Hong Kong H-shares (HKD) for the same issuer. Returns the per-bar "
        "basis, the FX-adjusted implied price, and the arbitrage direction "
        "(if any) when the basis exceeds the threshold."
    ),
    params_model=AHShareBasisParams,
    requires_dataset=True,
    tags=("arbitrage", "cross_market", "ah_share"),
)
def ah_share_basis_flow(
    df: Any, params: AHShareBasisParams, ctx: FlowContext
) -> FlowResult:
    from aqp.math.arbitrage import ah_share_basis

    if params.a_price_column not in df.columns:
        return FlowResult(
            flow="arbitrage.ah_share_basis",
            error=f"missing column: {params.a_price_column}",
        )
    if params.h_price_column not in df.columns:
        return FlowResult(
            flow="arbitrage.ah_share_basis",
            error=f"missing column: {params.h_price_column}",
        )

    rows: list[dict[str, Any]] = []
    arb_count = 0
    for idx in df.index[-params.preview_rows :]:
        try:
            a = float(df.loc[idx, params.a_price_column])
            h = float(df.loc[idx, params.h_price_column])
        except Exception:  # noqa: BLE001
            continue
        if params.fx_column and params.fx_column in df.columns:
            fx = float(df.loc[idx, params.fx_column])
        else:
            fx = params.fx_rate
        if fx <= 0:
            continue
        res = ah_share_basis(
            a,
            h,
            fx_rate=fx,
            conversion_ratio=params.conversion_ratio,
            transaction_cost_bps=params.transaction_cost_bps,
            threshold_bps=params.threshold_bps,
        )
        if res.is_arbitrage:
            arb_count += 1
        rows.append(
            {
                "ts": str(idx),
                "a_price": res.price_a,
                "h_price": res.price_b,
                "fx_rate": res.fx_rate,
                "implied_h_from_a": res.implied_price,
                "basis": res.basis,
                "basis_bps": res.basis_pct * 10000.0,
                "is_arbitrage": res.is_arbitrage,
                "arbitrage_direction": res.arbitrage_direction,
            }
        )
    return FlowResult(
        flow="arbitrage.ah_share_basis",
        metrics={
            "row_count": len(rows),
            "arbitrage_signal_count": arb_count,
            "conversion_ratio": params.conversion_ratio,
            "transaction_cost_bps": params.transaction_cost_bps,
        },
        rows=rows,
    )


# ---------------------------------------------------------------------------
# arbitrage.adr_basis
# ---------------------------------------------------------------------------


class ADRBasisParams(FlowParams):
    """Parameters for ``arbitrage.adr_basis``."""

    adr_price_column: str = Field(description="Column with ADR price in USD.")
    underlying_price_column: str = Field(
        description="Column with underlying foreign-equity price (home currency)."
    )
    fx_column: str | None = Field(default=None)
    fx_rate: float = Field(default=7.8, gt=0.0, description="home_ccy per USD")
    conversion_ratio: float = Field(default=1.0, gt=0.0)
    transaction_cost_bps: float = Field(default=30.0, ge=0.0)
    depository_fee_bps: float = Field(default=5.0, ge=0.0)
    threshold_bps: float = Field(default=80.0, ge=0.0)
    preview_rows: int = Field(default=200, ge=1, le=5000)


@register_analysis_flow(
    name="arbitrage.adr_basis",
    namespace="arbitrage",
    label="ADR / underlying basis monitor",
    description=(
        "Cross-market basis between a US-listed ADR and its foreign "
        "underlying. Reads the conversion ratio from the InstrumentADR "
        "row when available, falls back to the ``conversion_ratio`` param. "
        "Flags the arbitrage direction when the basis breaks the threshold."
    ),
    params_model=ADRBasisParams,
    requires_dataset=True,
    tags=("arbitrage", "cross_market", "adr"),
)
def adr_basis_flow(df: Any, params: ADRBasisParams, ctx: FlowContext) -> FlowResult:
    from aqp.math.arbitrage import adr_basis

    if params.adr_price_column not in df.columns:
        return FlowResult(
            flow="arbitrage.adr_basis",
            error=f"missing column: {params.adr_price_column}",
        )
    if params.underlying_price_column not in df.columns:
        return FlowResult(
            flow="arbitrage.adr_basis",
            error=f"missing column: {params.underlying_price_column}",
        )

    rows: list[dict[str, Any]] = []
    arb_count = 0
    for idx in df.index[-params.preview_rows :]:
        try:
            adr_px = float(df.loc[idx, params.adr_price_column])
            und_px = float(df.loc[idx, params.underlying_price_column])
        except Exception:  # noqa: BLE001
            continue
        if params.fx_column and params.fx_column in df.columns:
            fx = float(df.loc[idx, params.fx_column])
        else:
            fx = params.fx_rate
        if fx <= 0:
            continue
        res = adr_basis(
            adr_px,
            und_px,
            fx_rate=fx,
            conversion_ratio=params.conversion_ratio,
            transaction_cost_bps=params.transaction_cost_bps,
            depository_fee_bps=params.depository_fee_bps,
            threshold_bps=params.threshold_bps,
        )
        if res.is_arbitrage:
            arb_count += 1
        rows.append(
            {
                "ts": str(idx),
                "adr_price": res.price_b,
                "underlying_price": res.price_a,
                "fx_rate": res.fx_rate,
                "implied_adr": res.implied_price,
                "basis": res.basis,
                "basis_bps": res.basis_pct * 10000.0,
                "is_arbitrage": res.is_arbitrage,
                "arbitrage_direction": res.arbitrage_direction,
            }
        )
    return FlowResult(
        flow="arbitrage.adr_basis",
        metrics={
            "row_count": len(rows),
            "arbitrage_signal_count": arb_count,
            "conversion_ratio": params.conversion_ratio,
            "total_cost_bps": params.transaction_cost_bps + params.depository_fee_bps,
        },
        rows=rows,
    )
