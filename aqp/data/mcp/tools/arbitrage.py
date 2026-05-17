"""Phase 5 arbitrage DataMCP tools.

Exposes the Phase 4 :mod:`aqp.math.arbitrage` primitives as
agent-callable :class:`DataMCPTool` subclasses.

Tools:

* ``data.arbitrage.cointegration_pair`` -- two-series Engle-Granger
* ``data.arbitrage.johansen_basket`` -- multivariate cointegration
* ``data.arbitrage.ah_share_basis`` -- A/H share basis snapshot
* ``data.arbitrage.adr_underlying_basis`` -- ADR vs underlying basis
"""
from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from aqp.data.mcp.base import DataMCPTool, MCPToolContext, MCPToolResult
from aqp.data.mcp.policy import enforce_tenancy
from aqp.data.mcp.registry import register_data_mcp_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# data.arbitrage.cointegration_pair
# ---------------------------------------------------------------------------


class CointegrationPairInput(BaseModel):
    """Input schema for ``data.arbitrage.cointegration_pair``."""

    series_a: list[float] = Field(description="First series (typically prices).")
    series_b: list[float] = Field(description="Second series.")
    significance_level: float = Field(default=0.05, gt=0.0, lt=0.5)


@register_data_mcp_tool
class CointegrationPairTool(DataMCPTool):
    """Engle-Granger two-series cointegration test."""

    name = "data.arbitrage.cointegration_pair"
    description = (
        "Engle-Granger cointegration test on two series. Returns the "
        "p-value of the residual ADF test, the hedge ratio (OLS beta), "
        "and the latest spread + half-life. Use this BEFORE deploying "
        "a pair-trading strategy to confirm the spread is mean-reverting."
    )
    args_schema = CointegrationPairInput
    category = "arbitrage"
    tags = ("arbitrage", "cointegration", "pair_trading")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        series_a: list[float],
        series_b: list[float],
        significance_level: float = 0.05,
    ) -> MCPToolResult:
        try:
            import numpy as np
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"numpy/pandas unavailable: {exc}"
            )
        if len(series_a) != len(series_b):
            return MCPToolResult(
                ok=False, error="series_a and series_b must have equal length"
            )
        if len(series_a) < 30:
            return MCPToolResult(ok=False, error="need at least 30 observations")
        a = pd.Series(series_a, dtype=float)
        b = pd.Series(series_b, dtype=float)
        # Use existing aqp.data.cointegration.engle_granger when available
        try:
            from aqp.data.cointegration import engle_granger
            eg = engle_granger(a, b)
            from aqp.math.arbitrage import half_life

            spread = a - eg.hedge_ratio * b
            hl = half_life(spread)
            return MCPToolResult(
                ok=True,
                data={
                    "hedge_ratio": float(eg.hedge_ratio),
                    "adf_p_value": float(eg.adf_p_value),
                    "is_cointegrated": bool(eg.adf_p_value < significance_level),
                    "latest_spread": float(spread.iloc[-1]),
                    "spread_mean": float(spread.mean()),
                    "spread_std": float(spread.std()),
                    "half_life": hl.half_life,
                    "half_life_is_stationary": hl.is_stationary,
                },
                summary=(
                    f"hedge_ratio={eg.hedge_ratio:.4f}, p={eg.adf_p_value:.4f}, "
                    f"half_life={hl.half_life:.1f}"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"engle_granger failed: {exc}"
            )


# ---------------------------------------------------------------------------
# data.arbitrage.johansen_basket
# ---------------------------------------------------------------------------


class JohansenBasketInput(BaseModel):
    """Input schema for ``data.arbitrage.johansen_basket``."""

    series: dict[str, list[float]] = Field(
        description="Mapping of series-name to observations (>=2 series required, equal length)."
    )
    deterministic: Literal["constant", "trend", "none"] = Field(default="constant")
    k_ar_diff: int = Field(default=1, ge=0, le=10)


@register_data_mcp_tool
class JohansenBasketTool(DataMCPTool):
    """Johansen multivariate cointegration test."""

    name = "data.arbitrage.johansen_basket"
    description = (
        "Johansen test for multivariate cointegration across >=2 series. "
        "Returns the cointegration rank, the trace + max-eigenvalue stats "
        "with critical values, and the cointegrating vectors. Use this "
        "when looking for a stationary linear combination of 3+ assets "
        "(triangular arbitrage, basket vs index spread, ...)."
    )
    args_schema = JohansenBasketInput
    category = "arbitrage"
    tags = ("arbitrage", "cointegration", "johansen", "basket")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        series: dict[str, list[float]],
        deterministic: str = "constant",
        k_ar_diff: int = 1,
    ) -> MCPToolResult:
        try:
            import pandas as pd
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"pandas unavailable: {exc}")
        if len(series) < 2:
            return MCPToolResult(
                ok=False, error="need at least 2 series for Johansen"
            )
        lengths = {len(v) for v in series.values()}
        if len(lengths) != 1:
            return MCPToolResult(
                ok=False, error="all series must have equal length"
            )
        df = pd.DataFrame(series)
        from aqp.math.arbitrage import johansen_test

        result = johansen_test(
            df, deterministic=deterministic, k_ar_diff=k_ar_diff
        )
        if result.error:
            return MCPToolResult(ok=False, error=result.error)
        return MCPToolResult(
            ok=True,
            data={
                "rank": result.rank,
                "n_series": result.n_series,
                "deterministic": result.deterministic,
                "is_cointegrated_95": result.is_cointegrated_95,
                "is_cointegrated_99": result.is_cointegrated_99,
                "trace_stat": result.trace_stat,
                "max_eigen_stat": result.max_eigen_stat,
                "crit_trace_95": result.crit_trace_95,
                "crit_max_eigen_95": result.crit_max_eigen_95,
                "cointegrating_vectors": result.cointegrating_vectors,
                "eigenvalues": result.eig,
            },
            summary=f"rank={result.rank} of {result.n_series}, coint_95={result.is_cointegrated_95}",
        )


# ---------------------------------------------------------------------------
# data.arbitrage.ah_share_basis
# ---------------------------------------------------------------------------


class AHShareBasisInput(BaseModel):
    """Input schema for ``data.arbitrage.ah_share_basis``."""

    a_price: float = Field(gt=0, description="A-share price in CNY")
    h_price: float = Field(gt=0, description="H-share price in HKD")
    fx_rate: float = Field(default=0.917, gt=0, description="CNY per HKD")
    conversion_ratio: float = Field(default=1.0, gt=0)
    transaction_cost_bps: float = Field(default=20.0, ge=0)
    threshold_bps: float = Field(default=100.0, ge=0)


@register_data_mcp_tool
class AHShareBasisTool(DataMCPTool):
    """A-share <-> H-share cross-market basis snapshot."""

    name = "data.arbitrage.ah_share_basis"
    description = (
        "Cross-market basis between mainland A-shares (CNY) and Hong "
        "Kong H-shares (HKD) for the same issuer. Returns the basis "
        "in absolute and bps terms, the FX-adjusted implied price, "
        "and the arbitrage direction if the basis exceeds the threshold."
    )
    args_schema = AHShareBasisInput
    category = "arbitrage"
    tags = ("arbitrage", "cross_market", "ah_share", "china")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(self, *, ctx: MCPToolContext, **arguments: Any) -> MCPToolResult:
        from aqp.math.arbitrage import ah_share_basis

        res = ah_share_basis(
            a_price=float(arguments["a_price"]),
            h_price=float(arguments["h_price"]),
            fx_rate=float(arguments.get("fx_rate", 0.917)),
            conversion_ratio=float(arguments.get("conversion_ratio", 1.0)),
            transaction_cost_bps=float(arguments.get("transaction_cost_bps", 20.0)),
            threshold_bps=float(arguments.get("threshold_bps", 100.0)),
        )
        return MCPToolResult(
            ok=True,
            data={
                "a_price": res.price_a,
                "h_price": res.price_b,
                "implied_h_from_a": res.implied_price,
                "fx_rate": res.fx_rate,
                "conversion_ratio": res.conversion_ratio,
                "basis": res.basis,
                "basis_bps": res.basis_pct * 10000.0,
                "cost_adjusted_basis": res.cost_adjusted_basis,
                "is_arbitrage": res.is_arbitrage,
                "arbitrage_direction": res.arbitrage_direction,
            },
            summary=f"basis={res.basis_pct*10000:.1f}bps, direction={res.arbitrage_direction}",
        )


# ---------------------------------------------------------------------------
# data.arbitrage.adr_underlying_basis
# ---------------------------------------------------------------------------


class ADRUnderlyingBasisInput(BaseModel):
    """Input schema for ``data.arbitrage.adr_underlying_basis``."""

    adr_vt_symbol: str = Field(description="ADR's vt_symbol (e.g. 'BABA.NYSE').")
    adr_price: float = Field(gt=0)
    underlying_price: float = Field(gt=0)
    fx_rate: float = Field(gt=0)
    conversion_ratio: float | None = Field(
        default=None,
        description="Override the conversion_ratio. When None, read from the InstrumentADR row.",
    )
    transaction_cost_bps: float = Field(default=30.0, ge=0)
    depository_fee_bps: float = Field(default=5.0, ge=0)
    threshold_bps: float = Field(default=80.0, ge=0)


@register_data_mcp_tool
class ADRUnderlyingBasisTool(DataMCPTool):
    """ADR / GDR <-> underlying foreign equity basis snapshot.

    Reads the ``conversion_ratio`` from the
    :class:`aqp.persistence.models_instruments.InstrumentADR` row when
    the caller doesn't override it -- this is the Phase 1-1-Phase 4
    integration the report calls for.
    """

    name = "data.arbitrage.adr_underlying_basis"
    description = (
        "Cross-market basis between an ADR (USD) and its foreign "
        "underlying (home currency). The conversion_ratio is read "
        "directly from the InstrumentADR row when present, otherwise "
        "the caller's override is used. Flags arbitrage direction "
        "when the basis exceeds the threshold."
    )
    args_schema = ADRUnderlyingBasisInput
    category = "arbitrage"
    tags = ("arbitrage", "cross_market", "adr", "gdr")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        adr_vt_symbol: str,
        adr_price: float,
        underlying_price: float,
        fx_rate: float,
        conversion_ratio: float | None = None,
        transaction_cost_bps: float = 30.0,
        depository_fee_bps: float = 5.0,
        threshold_bps: float = 80.0,
    ) -> MCPToolResult:
        from aqp.math.arbitrage import adr_basis

        if conversion_ratio is None:
            conversion_ratio = self._lookup_conversion_ratio(adr_vt_symbol)
        if conversion_ratio is None:
            return MCPToolResult(
                ok=False,
                error=(
                    "conversion_ratio not provided and no InstrumentADR row "
                    f"found for {adr_vt_symbol!r}"
                ),
            )
        res = adr_basis(
            adr_price=float(adr_price),
            underlying_price=float(underlying_price),
            fx_rate=float(fx_rate),
            conversion_ratio=float(conversion_ratio),
            transaction_cost_bps=float(transaction_cost_bps),
            depository_fee_bps=float(depository_fee_bps),
            threshold_bps=float(threshold_bps),
        )
        return MCPToolResult(
            ok=True,
            data={
                "adr_vt_symbol": adr_vt_symbol,
                "adr_price": res.price_b,
                "underlying_price": res.price_a,
                "implied_adr": res.implied_price,
                "fx_rate": res.fx_rate,
                "conversion_ratio": res.conversion_ratio,
                "basis": res.basis,
                "basis_bps": res.basis_pct * 10000.0,
                "cost_adjusted_basis": res.cost_adjusted_basis,
                "is_arbitrage": res.is_arbitrage,
                "arbitrage_direction": res.arbitrage_direction,
            },
            summary=(
                f"basis={res.basis_pct*10000:.1f}bps, "
                f"direction={res.arbitrage_direction}, conversion={res.conversion_ratio}"
            ),
        )

    def _lookup_conversion_ratio(self, adr_vt_symbol: str) -> float | None:
        try:
            from sqlalchemy import select

            from aqp.persistence.db import get_session
            from aqp.persistence.models import Instrument
            from aqp.persistence.models_instruments import InstrumentADR, InstrumentGDR
        except Exception:  # noqa: BLE001
            return None
        with get_session() as session:
            inst_id = session.execute(
                select(Instrument.id).where(Instrument.vt_symbol == adr_vt_symbol)
            ).scalar_one_or_none()
            if inst_id is None:
                return None
            ratio = session.execute(
                select(InstrumentADR.conversion_ratio).where(InstrumentADR.id == inst_id)
            ).scalar_one_or_none()
            if ratio is not None:
                return float(ratio)
            ratio = session.execute(
                select(InstrumentGDR.conversion_ratio).where(InstrumentGDR.id == inst_id)
            ).scalar_one_or_none()
            if ratio is not None:
                return float(ratio)
            return None


__all__ = [
    "ADRUnderlyingBasisTool",
    "AHShareBasisTool",
    "CointegrationPairTool",
    "JohansenBasketTool",
]
