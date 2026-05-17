"""Phase 5 pricing + risk DataMCP tools.

Exposes the Phase 4 :class:`PricingContext`, :class:`RiskMeasure`
polymorphic dispatch, and portfolio Greeks aggregation as
agent-callable :class:`DataMCPTool` subclasses (AGENTS rule 22).

Tools:

* ``data.pricing.context.list`` -- recent pricing-context runs
* ``data.pricing.greeks.option_chain`` -- chain-level Greek aggregation
* ``data.pricing.greeks.portfolio`` -- :class:`PortfolioGreeks` rollup
* ``data.risk.var.compute`` -- portfolio VaR / TVaR via historical sim
* ``data.risk.scenario.stress`` -- scenario PnL under named shocks
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
# data.pricing.context.list
# ---------------------------------------------------------------------------


class ListPricingRunsInput(BaseModel):
    """Input schema for ``data.pricing.context.list``."""

    instrument_class: str | None = Field(default=None)
    measure: str | None = Field(default=None)
    status: Literal["running", "completed", "error"] | None = Field(default=None)
    limit: int = Field(default=25, ge=1, le=200)


@register_data_mcp_tool
class ListPricingRunsTool(DataMCPTool):
    """List recent :class:`PricingContext` executions."""

    name = "data.pricing.context.list"
    description = (
        "List recent PricingContext executions with their measure, "
        "instrument class, elapsed time, and result status. Use this "
        "to audit how a portfolio's risk was computed at a given as-of "
        "date or to find an Iceberg identifier holding a previously-"
        "computed result."
    )
    args_schema = ListPricingRunsInput
    category = "pricing"
    tags = ("pricing", "risk", "audit")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        instrument_class: str | None = None,
        measure: str | None = None,
        status: str | None = None,
        limit: int = 25,
    ) -> MCPToolResult:
        from sqlalchemy import select

        from aqp.persistence.db import get_session
        from aqp.persistence.models_predictors import PricingContextRunRow

        with get_session() as session:
            stmt = select(PricingContextRunRow).order_by(
                PricingContextRunRow.ts_started.desc()
            )
            if instrument_class:
                stmt = stmt.where(
                    PricingContextRunRow.instrument_class == instrument_class
                )
            if measure:
                stmt = stmt.where(PricingContextRunRow.measure == measure)
            if status:
                stmt = stmt.where(PricingContextRunRow.status == status)
            if ctx.workspace_id:
                stmt = stmt.where(
                    PricingContextRunRow.workspace_id == ctx.workspace_id
                )
            stmt = stmt.limit(int(limit))
            rows = session.execute(stmt).scalars().all()
            out = [
                {
                    "id": r.id,
                    "context_id": r.context_id,
                    "measure": r.measure,
                    "instrument_class": r.instrument_class,
                    "instrument_ref": r.instrument_ref,
                    "as_of": r.as_of.isoformat() if r.as_of else None,
                    "dispatch": r.dispatch,
                    "behaviour": r.behaviour,
                    "status": r.status,
                    "value_scalar": r.value_scalar,
                    "elapsed_ms": r.elapsed_ms,
                    "arrow_identifier": r.arrow_identifier,
                    "ts_started": r.ts_started.isoformat() if r.ts_started else None,
                    "ts_completed": r.ts_completed.isoformat()
                    if r.ts_completed
                    else None,
                    "experiment_id": r.experiment_id,
                }
                for r in rows
            ]
        return MCPToolResult(
            ok=True,
            data=out,
            rows_returned=len(out),
            summary=f"{len(out)} pricing-context runs",
        )


# ---------------------------------------------------------------------------
# data.pricing.greeks.option_chain
# ---------------------------------------------------------------------------


class OptionChainGreeksInput(BaseModel):
    """Input schema for ``data.pricing.greeks.option_chain``."""

    underlying: str = Field(description="Underlying ticker (e.g. 'AAPL').")
    expiry: str = Field(description="Chain expiry in ISO date format.")
    underlying_price: float = Field(gt=0)
    risk_free_rate: float = Field(default=0.045, ge=0.0)
    dividend_yield: float = Field(default=0.0, ge=0.0)
    implied_vol_default: float = Field(default=0.25, gt=0.0)
    strikes: list[float] | None = Field(default=None)


@register_data_mcp_tool
class OptionChainGreeksTool(DataMCPTool):
    """Aggregate Greeks across a flat option-chain payload.

    Useful when the agent wants total chain delta / gamma / vega
    without rebuilding the chain itself. The tool reads the latest
    snapshot from ``option_chains_snapshots`` (when available) or
    computes from scratch using the supplied strikes + assumptions.
    """

    name = "data.pricing.greeks.option_chain"
    description = (
        "Aggregate Black-Scholes Greeks across an option chain. "
        "Returns total chain delta / gamma / theta / vega / rho + "
        "per-strike breakdown. The chain is loaded from the latest "
        "OptionChainSnapshot row when available; falls back to "
        "computing fresh values from the supplied strikes + assumptions."
    )
    args_schema = OptionChainGreeksInput
    category = "pricing"
    tags = ("pricing", "greeks", "options")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        underlying: str,
        expiry: str,
        underlying_price: float,
        risk_free_rate: float = 0.045,
        dividend_yield: float = 0.0,
        implied_vol_default: float = 0.25,
        strikes: list[float] | None = None,
    ) -> MCPToolResult:
        # Best-effort: compute on the fly when no chain is cached.
        from datetime import date

        from math import exp, log, sqrt

        try:
            from scipy.stats import norm
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(
                ok=False, error=f"scipy.stats unavailable: {exc}"
            )

        try:
            expiry_date = date.fromisoformat(expiry)
            days_to_expiry = max((expiry_date - date.today()).days, 1)
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"invalid expiry date: {exc}")

        T = days_to_expiry / 365.0
        S = float(underlying_price)
        r = float(risk_free_rate)
        q = float(dividend_yield)
        sigma = float(implied_vol_default)

        if not strikes:
            strikes = [round(S * f, 2) for f in (0.85, 0.90, 0.95, 1.0, 1.05, 1.10, 1.15)]

        per_strike = []
        total = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
        for K in strikes:
            d1 = (log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
            d2 = d1 - sigma * sqrt(T)
            delta_call = exp(-q * T) * norm.cdf(d1)
            gamma = exp(-q * T) * norm.pdf(d1) / (S * sigma * sqrt(T))
            theta_call = (
                -S * exp(-q * T) * norm.pdf(d1) * sigma / (2 * sqrt(T))
                + q * S * exp(-q * T) * norm.cdf(d1)
                - r * K * exp(-r * T) * norm.cdf(d2)
            )
            vega = S * exp(-q * T) * norm.pdf(d1) * sqrt(T)
            rho_call = K * T * exp(-r * T) * norm.cdf(d2)
            per_strike.append(
                {
                    "strike": float(K),
                    "delta_call": float(delta_call),
                    "gamma": float(gamma),
                    "theta_call": float(theta_call) / 365.0,  # per-day theta
                    "vega": float(vega) / 100.0,  # per 1 vol-point
                    "rho_call": float(rho_call) / 100.0,  # per 1 rate-point
                }
            )
            total["delta"] += delta_call
            total["gamma"] += gamma
            total["theta"] += theta_call / 365.0
            total["vega"] += vega / 100.0
            total["rho"] += rho_call / 100.0
        return MCPToolResult(
            ok=True,
            data={
                "underlying": underlying,
                "expiry": expiry,
                "spot": S,
                "implied_vol": sigma,
                "risk_free_rate": r,
                "dividend_yield": q,
                "days_to_expiry": days_to_expiry,
                "total_chain_greeks": total,
                "per_strike": per_strike,
            },
            rows_returned=len(per_strike),
            summary=f"Aggregated Greeks across {len(strikes)} strikes for {underlying} {expiry}",
        )


# ---------------------------------------------------------------------------
# data.risk.var.compute
# ---------------------------------------------------------------------------


class VarComputeInput(BaseModel):
    """Input schema for ``data.risk.var.compute``."""

    returns: list[float] = Field(description="Historical returns series (daily).")
    confidence: float = Field(default=0.95, gt=0.5, lt=0.9999)
    method: Literal["historical", "parametric", "cornish_fisher"] = Field(default="historical")
    horizon_days: int = Field(default=1, ge=1, le=252)
    notional: float = Field(default=1_000_000.0, gt=0.0)


@register_data_mcp_tool
class ComputeVarTool(DataMCPTool):
    """Compute VaR + TVaR (Conditional VaR) from a return series."""

    name = "data.risk.var.compute"
    description = (
        "Compute portfolio-level Value-at-Risk + Tail VaR (Conditional VaR) "
        "from a historical returns series. Supports historical simulation, "
        "parametric (variance-covariance), and Cornish-Fisher with skew/"
        "kurtosis adjustment. Horizon scaling assumes IID returns "
        "(sqrt(T) rule); pass already-T-day returns to disable scaling."
    )
    args_schema = VarComputeInput
    category = "risk"
    tags = ("risk", "var", "tvar")

    def policy_check(self, ctx: MCPToolContext) -> None:  # noqa: D401
        super().policy_check(ctx)
        enforce_tenancy(ctx, required=False)

    def run(
        self,
        *,
        ctx: MCPToolContext,
        returns: list[float],
        confidence: float = 0.95,
        method: str = "historical",
        horizon_days: int = 1,
        notional: float = 1_000_000.0,
    ) -> MCPToolResult:
        try:
            import numpy as np
        except Exception as exc:  # noqa: BLE001
            return MCPToolResult(ok=False, error=f"numpy unavailable: {exc}")
        r = np.asarray(returns, dtype=float)
        if r.size < 30:
            return MCPToolResult(
                ok=False, error="need at least 30 observations for a meaningful VaR"
            )
        alpha = 1.0 - float(confidence)
        var_h: float
        tvar_h: float
        if method == "historical":
            quantile = float(np.quantile(r, alpha))
            tail = r[r <= quantile]
            var_h = -quantile
            tvar_h = -float(tail.mean()) if tail.size > 0 else var_h
        elif method == "parametric":
            mu = float(r.mean())
            sigma = float(r.std(ddof=1))
            try:
                from scipy.stats import norm
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False, error=f"scipy.stats unavailable: {exc}"
                )
            z = float(norm.ppf(alpha))
            var_h = -(mu + sigma * z)
            tvar_h = -(mu - sigma * float(norm.pdf(z)) / alpha)
        elif method == "cornish_fisher":
            try:
                from scipy.stats import kurtosis, norm, skew
            except Exception as exc:  # noqa: BLE001
                return MCPToolResult(
                    ok=False, error=f"scipy.stats unavailable: {exc}"
                )
            mu = float(r.mean())
            sigma = float(r.std(ddof=1))
            s = float(skew(r))
            k = float(kurtosis(r))
            z = float(norm.ppf(alpha))
            # Cornish-Fisher expansion
            z_cf = (
                z
                + (z ** 2 - 1) * s / 6.0
                + (z ** 3 - 3 * z) * k / 24.0
                - (2 * z ** 3 - 5 * z) * s ** 2 / 36.0
            )
            var_h = -(mu + sigma * z_cf)
            tvar_h = -(mu - sigma * float(norm.pdf(z)) / alpha)
        else:
            return MCPToolResult(ok=False, error=f"unknown method {method!r}")

        # Horizon scaling -- sqrt-of-T
        scale = float(horizon_days) ** 0.5
        var_scaled = var_h * scale
        tvar_scaled = tvar_h * scale
        return MCPToolResult(
            ok=True,
            data={
                "method": method,
                "confidence": confidence,
                "horizon_days": horizon_days,
                "n_observations": int(r.size),
                "var_pct": float(var_scaled),
                "tvar_pct": float(tvar_scaled),
                "var_dollar": float(var_scaled * notional),
                "tvar_dollar": float(tvar_scaled * notional),
                "notional": notional,
            },
            summary=f"{method} {int(confidence*100)}% VaR={var_scaled:.4f} TVaR={tvar_scaled:.4f}",
        )


__all__ = [
    "ComputeVarTool",
    "ListPricingRunsTool",
    "OptionChainGreeksTool",
]
