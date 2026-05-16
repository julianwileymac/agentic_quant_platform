"""Optimal-control analysis flows.

Wraps the JAX-compiled solvers from :mod:`aqp.optimal_control` and the
Lucic-Tse portfolio MM solver from :mod:`aqp.options.portfolio_mm` so
the lab UI gets auto-generated forms and ``AnalysisRuntime`` can persist
the outputs to ``aqp_gold_analysis_optimal_control``.

Catalogue
=========

- ``optimal_control.avellaneda_stoikov_quotes`` — single-asset finite-
  horizon AvSt quote schedule across an inventory grid.
- ``optimal_control.cartea_jaimungal_liquidation`` — RK4 solve of the
  linear-quadratic ansatz for inventory-penalised optimal liquidation.
- ``optimal_control.lucic_tse_portfolio_quotes`` — Lucic-Tse portfolio-
  level quote matrix across a multi-strike option chain.
- ``optimal_control.toxicity_regime`` — VPIN + cancellation-ratio +
  microprice-variance composite toxicity signal returning a regime
  label and a suggested ``gamma`` multiplier.

The flows are intentionally thin facades: every numeric line lives in
:mod:`aqp.optimal_control` or :mod:`aqp.options.portfolio_mm`, so
re-tuning the math does not touch the flow code.
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
# Avellaneda-Stoikov optimal quotes
# ---------------------------------------------------------------------------


class AvSTQuoteParams(FlowParams):
    """Parameters for ``optimal_control.avellaneda_stoikov_quotes``."""

    mid_price: float = Field(default=100.0, gt=0.0, description="Current mid price")
    inventory_min: float = Field(default=-50.0)
    inventory_max: float = Field(default=50.0)
    inventory_step: float = Field(default=5.0, gt=0.0)
    gamma: float = Field(default=0.1, gt=0.0, description="Risk-aversion coefficient")
    sigma: float = Field(default=0.01, gt=0.0, description="Mid-price volatility")
    k: float = Field(default=1.5, gt=0.0, description="Cox-process liquidity parameter")
    T_minus_t: float = Field(default=1.0, gt=0.0, description="Time-to-horizon")


@register_analysis_flow(
    name="optimal_control.avellaneda_stoikov_quotes",
    namespace="optimal_control",
    label="Avellaneda-Stoikov quote schedule",
    description=(
        "Optimal bid/ask quotes across an inventory grid using the JAX-"
        "compiled Avellaneda-Stoikov solver. The output table is the "
        "quote schedule a market-making strategy posts at each inventory "
        "level, ready to plug into aqp.strategies.hft.AvellanedaStoikovMM."
    ),
    params_model=AvSTQuoteParams,
    requires_dataset=False,
    tags=("optimal_control", "market_making", "hjb"),
    optional_dependencies=("jax", "jaxlib"),
)
def avellaneda_stoikov_quotes_flow(
    df: Any, params: AvSTQuoteParams, ctx: FlowContext
) -> FlowResult:
    from aqp.optimal_control.hjb_solver import solve_avst

    inventory_grid = np.arange(
        params.inventory_min,
        params.inventory_max + params.inventory_step,
        params.inventory_step,
        dtype=float,
    )
    out = solve_avst(
        mid_price=params.mid_price,
        inventory_grid=inventory_grid,
        gamma=params.gamma,
        sigma=params.sigma,
        k=params.k,
        T_minus_t=params.T_minus_t,
    )
    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [r["inventory"] for r in out["rows"]],
                "y": [r["bid"] for r in out["rows"]],
                "name": "bid",
            },
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [r["inventory"] for r in out["rows"]],
                "y": [r["ask"] for r in out["rows"]],
                "name": "ask",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "x": [r["inventory"] for r in out["rows"]],
                "y": [r["reservation_price"] for r in out["rows"]],
                "name": "reservation",
            },
        ],
        "layout": {
            "title": "Avellaneda-Stoikov quote schedule",
            "xaxis": {"title": "inventory"},
            "yaxis": {"title": "price"},
        },
    }
    return FlowResult(
        flow="optimal_control.avellaneda_stoikov_quotes",
        metrics=out["metrics"],
        rows=out["rows"],
        chart=chart,
        arrow_table=coerce_arrow(out["rows"]),
    )


# ---------------------------------------------------------------------------
# Cartea-Jaimungal optimal liquidation
# ---------------------------------------------------------------------------


class CJLiquidationParams(FlowParams):
    """Parameters for ``optimal_control.cartea_jaimungal_liquidation``."""

    horizon: float = Field(default=1.0, gt=0.0, description="Total liquidation horizon")
    initial_inventory: float = Field(default=100.0)
    sigma: float = Field(default=0.01, gt=0.0)
    phi: float = Field(default=1e-4, ge=0.0, description="Running inventory penalty")
    alpha: float = Field(default=1e-3, ge=0.0, description="Terminal inventory penalty")
    kappa: float = Field(default=1.0, gt=0.0, description="Temporary impact coefficient")
    n_steps: int = Field(default=200, ge=10, le=10_000)


@register_analysis_flow(
    name="optimal_control.cartea_jaimungal_liquidation",
    namespace="optimal_control",
    label="Cartea-Jaimungal liquidation HJB",
    description=(
        "Solve the Cartea-Jaimungal-Penalva (2015) optimal-liquidation "
        "HJB via RK4 on the linear-quadratic ansatz coefficients. "
        "Returns the value-function coefficients (h0, h1, h2) and a "
        "forward-simulated inventory + cash trajectory under the "
        "feedback-optimal trading rate."
    ),
    params_model=CJLiquidationParams,
    requires_dataset=False,
    tags=("optimal_control", "execution", "hjb"),
)
def cartea_jaimungal_liquidation_flow(
    df: Any, params: CJLiquidationParams, ctx: FlowContext
) -> FlowResult:
    from aqp.optimal_control.hjb_solver import solve_cj

    out = solve_cj(
        horizon=params.horizon,
        initial_inventory=params.initial_inventory,
        sigma=params.sigma,
        phi=params.phi,
        alpha=params.alpha,
        kappa=params.kappa,
        n_steps=params.n_steps,
    )
    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines",
                "x": [r["t"] for r in out["rows"]],
                "y": [r["inventory"] for r in out["rows"]],
                "name": "inventory",
                "yaxis": "y",
            },
            {
                "type": "scatter",
                "mode": "lines",
                "x": [r["t"] for r in out["rows"]],
                "y": [r["trading_rate"] for r in out["rows"]],
                "name": "trading rate",
                "yaxis": "y2",
            },
        ],
        "layout": {
            "title": "Cartea-Jaimungal optimal liquidation",
            "xaxis": {"title": "t"},
            "yaxis": {"title": "inventory"},
            "yaxis2": {"title": "rate", "overlaying": "y", "side": "right"},
        },
    }
    return FlowResult(
        flow="optimal_control.cartea_jaimungal_liquidation",
        metrics=out["metrics"],
        rows=out["rows"][:500],
        chart=chart,
        arrow_table=coerce_arrow(out["rows"]),
    )


# ---------------------------------------------------------------------------
# Lucic-Tse portfolio options market making
# ---------------------------------------------------------------------------


class LucicTseFlowParams(FlowParams):
    """Parameters for ``optimal_control.lucic_tse_portfolio_quotes``.

    Pass either a flat strikes/expiries spec (we generate a synthetic
    BSM mid surface internally) or pre-computed ``mid_quotes`` /
    ``gamma_surface`` / ``vega_surface`` arrays. The first form is
    intended for lab exploration; the second for production handoff.
    """

    spot: float = Field(default=100.0, gt=0.0)
    strikes: list[float] = Field(default_factory=lambda: [90.0, 95.0, 100.0, 105.0, 110.0])
    expiries: list[float] = Field(default_factory=lambda: [0.05, 0.1, 0.25, 0.5])
    rate: float = Field(default=0.0)
    realized_vol: float = Field(default=0.20, gt=0.0)
    implied_vol: float = Field(default=0.22, gt=0.0)
    inventory_per_strike: float = Field(default=0.0, description="Constant inventory per strike (toy)")
    gamma_inv: float = Field(default=0.05, gt=0.0)
    base_spread: float = Field(default=0.05, gt=0.0)
    hedge_cost: float = Field(default=0.001, ge=0.0)
    option_type: Literal["call", "put"] = "call"


@register_analysis_flow(
    name="optimal_control.lucic_tse_portfolio_quotes",
    namespace="optimal_control",
    label="Lucic-Tse portfolio options MM",
    description=(
        "Lucic-Tse (2024-2026) closed-form Riccati solver for portfolio-"
        "level options market making. Generates a synthetic BSM Greek "
        "surface from the strikes x expiries grid, applies the vol-arb "
        "alpha and inventory-skew adjustments, and returns the optimal "
        "bid/ask quote matrices for the whole chain."
    ),
    params_model=LucicTseFlowParams,
    requires_dataset=False,
    tags=("optimal_control", "options", "market_making", "lucic_tse"),
    optional_dependencies=("jax", "jaxlib", "fast-vollib"),
)
def lucic_tse_portfolio_quotes_flow(
    df: Any, params: LucicTseFlowParams, ctx: FlowContext
) -> FlowResult:
    from aqp.analysis.pricing import greeks_grid
    from aqp.options.portfolio_mm import (
        LucicTseParams,
        compute_lucic_tse_quotes,
    )

    strikes = np.asarray(params.strikes, dtype=float)
    expiries = np.asarray(params.expiries, dtype=float)
    if strikes.size == 0 or expiries.size == 0:
        return FlowResult(
            flow="optimal_control.lucic_tse_portfolio_quotes",
            error="strikes and expiries must be non-empty",
        )

    grid = greeks_grid(
        spot=params.spot,
        strikes=strikes,
        expiries=expiries,
        rate=params.rate,
        vol=params.implied_vol,
        option_type=params.option_type,
    )
    mid_quotes = grid["price"]
    gamma_surface = grid["gamma"]
    vega_surface = grid["vega"]
    inventory = np.full_like(mid_quotes, fill_value=params.inventory_per_strike)

    p = LucicTseParams(
        gamma_inv=params.gamma_inv,
        base_spread=params.base_spread,
        hedge_cost=params.hedge_cost,
    )
    quotes = compute_lucic_tse_quotes(
        spot=params.spot,
        mid_quotes=mid_quotes,
        gamma_surface=gamma_surface,
        vega_surface=vega_surface,
        realized_vol=params.realized_vol,
        implied_vol=np.full_like(mid_quotes, fill_value=params.implied_vol),
        inventory=inventory,
        params=p,
    )

    rows: list[dict[str, Any]] = []
    for i, t in enumerate(expiries):
        for j, k in enumerate(strikes):
            rows.append(
                {
                    "expiry": float(t),
                    "strike": float(k),
                    "mid": float(mid_quotes[i, j]),
                    "bid": float(quotes.bid[i, j]),
                    "ask": float(quotes.ask[i, j]),
                    "half_spread": float(quotes.half_spread[i, j]),
                    "inventory_skew": float(quotes.inventory_skew[i, j]),
                    "expected_pnl": float(quotes.expected_pnl[i, j]),
                    "gamma": float(gamma_surface[i, j]),
                    "vega": float(vega_surface[i, j]),
                }
            )
    chart = {
        "data": [
            {
                "type": "heatmap",
                "x": list(map(float, strikes.tolist())),
                "y": list(map(float, expiries.tolist())),
                "z": (quotes.ask - quotes.bid).tolist(),
                "colorbar": {"title": "ask-bid"},
                "name": "spread",
            }
        ],
        "layout": {
            "title": "Lucic-Tse optimal spread surface",
            "xaxis": {"title": "strike"},
            "yaxis": {"title": "expiry"},
        },
    }
    metrics = {
        **quotes.to_summary(),
        "spot": float(params.spot),
        "realized_vol": float(params.realized_vol),
        "implied_vol": float(params.implied_vol),
        "gamma_inv": float(params.gamma_inv),
        "base_spread": float(params.base_spread),
        "hedge_cost": float(params.hedge_cost),
    }
    return FlowResult(
        flow="optimal_control.lucic_tse_portfolio_quotes",
        metrics=metrics,
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Toxicity regime detector
# ---------------------------------------------------------------------------


class ToxicityRegimeParams(FlowParams):
    """Parameters for ``optimal_control.toxicity_regime``.

    The flow consumes a recent slice of microstructure data (top-of-
    book quotes + trade flow) and returns a composite toxicity score.
    A high score = toxic adverse-selection regime → recommend a
    higher inventory penalty (gamma_multiplier > 1.0) and a smaller
    order size.
    """

    buy_volume_column: str = "buy_volume"
    sell_volume_column: str = "sell_volume"
    bid_qty_column: str = "bid_qty"
    ask_qty_column: str = "ask_qty"
    bid_price_column: str = "bid_price"
    ask_price_column: str = "ask_price"
    cancellation_column: str | None = None
    n_buckets: int = Field(default=50, ge=2, le=2000)
    toxic_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


@register_analysis_flow(
    name="optimal_control.toxicity_regime",
    namespace="optimal_control",
    label="Toxicity regime detector",
    description=(
        "Composite VPIN + microprice-variance + cancellation-ratio "
        "toxicity score. Returns a regime label "
        "(``benign|elevated|toxic``) and a suggested gamma multiplier "
        "(1.0 / 1.25 / 1.5x) the strategy YAML mutator can apply."
    ),
    params_model=ToxicityRegimeParams,
    requires_dataset=True,
    tags=("optimal_control", "microstructure", "toxicity", "regime"),
)
def toxicity_regime_flow(
    df: pd.DataFrame, params: ToxicityRegimeParams, ctx: FlowContext
) -> FlowResult:
    from aqp.data.microstructure import microprice, vpin

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    needed_volumes = {params.buy_volume_column, params.sell_volume_column}
    if not needed_volumes.issubset(df.columns):
        return FlowResult(
            flow="optimal_control.toxicity_regime",
            error=f"missing volume columns; need {sorted(needed_volumes)}",
        )

    vpin_series = vpin(
        df[params.buy_volume_column],
        df[params.sell_volume_column],
        n_buckets=int(params.n_buckets),
    )
    vpin_recent = float(np.nan_to_num(vpin_series.tail(20).mean(), nan=0.0))

    micro_var = float("nan")
    if {
        params.bid_price_column,
        params.ask_price_column,
        params.bid_qty_column,
        params.ask_qty_column,
    }.issubset(df.columns):
        mp = microprice(
            df[params.bid_price_column],
            df[params.ask_price_column],
            df[params.bid_qty_column],
            df[params.ask_qty_column],
        )
        if isinstance(mp, pd.Series):
            mid = (df[params.bid_price_column] + df[params.ask_price_column]) / 2.0
            micro_var = float(np.nan_to_num((mp - mid).var(), nan=0.0))

    cancel_ratio = 0.0
    if params.cancellation_column and params.cancellation_column in df.columns:
        total_orders = (
            df[params.cancellation_column].abs()
            + df[params.buy_volume_column].abs()
            + df[params.sell_volume_column].abs()
        )
        cancel_ratio = float(
            (df[params.cancellation_column].abs() / total_orders.replace(0, np.nan))
            .dropna()
            .tail(50)
            .mean()
        )
        cancel_ratio = 0.0 if np.isnan(cancel_ratio) else cancel_ratio

    # Composite score in [0, 1]: 60% VPIN + 25% normalised microprice
    # variance + 15% cancellation ratio.
    micro_norm = float(min(1.0, max(0.0, micro_var * 1e3))) if not np.isnan(micro_var) else 0.0
    composite = 0.6 * vpin_recent + 0.25 * micro_norm + 0.15 * cancel_ratio

    if composite >= params.toxic_threshold:
        label = "toxic"
        gamma_multiplier = 1.5
        order_size_multiplier = 0.5
    elif composite >= 0.5 * params.toxic_threshold:
        label = "elevated"
        gamma_multiplier = 1.25
        order_size_multiplier = 0.75
    else:
        label = "benign"
        gamma_multiplier = 1.0
        order_size_multiplier = 1.0

    metrics = {
        "regime": label,
        "composite_score": float(composite),
        "vpin_recent": float(vpin_recent),
        "microprice_variance": float(micro_var) if not np.isnan(micro_var) else None,
        "cancellation_ratio": float(cancel_ratio),
        "gamma_multiplier": float(gamma_multiplier),
        "order_size_multiplier": float(order_size_multiplier),
        "n_rows": int(len(df)),
        "toxic_threshold": float(params.toxic_threshold),
    }
    rows = [
        {
            "regime": label,
            "composite_score": float(composite),
            "vpin": float(vpin_recent),
            "gamma_multiplier": float(gamma_multiplier),
            "order_size_multiplier": float(order_size_multiplier),
        }
    ]
    return FlowResult(
        flow="optimal_control.toxicity_regime",
        metrics=metrics,
        rows=rows,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Obizhaeva-Wang dynamic optimal execution
# ---------------------------------------------------------------------------


class OWLiquidationParams(FlowParams):
    """Parameters for ``optimal_control.obizhaeva_wang_solve``.

    The defaults reproduce the canonical 1-share / 1-period example
    from Obizhaeva & Wang (2013) so a flow run with no arguments
    yields a recognisable trajectory.
    """

    total_shares: float = Field(default=1.0, description="Quantity to liquidate")
    horizon: float = Field(default=1.0, gt=0.0, description="Liquidation horizon")
    resilience: float = Field(default=1.0, gt=0.0, description="Book resilience rho")
    impact_coeff: float = Field(default=1.0, gt=0.0, description="Linear-impact lambda")
    grid_points: int = Field(default=64, ge=2, le=4_096)
    rho_sweep_low: float = Field(default=0.1, gt=0.0, description="Sensitivity sweep low end")
    rho_sweep_high: float = Field(default=5.0, gt=0.0, description="Sensitivity sweep high end")
    rho_sweep_points: int = Field(default=32, ge=4, le=512)


@register_analysis_flow(
    name="optimal_control.obizhaeva_wang_solve",
    namespace="optimal_control",
    label="Obizhaeva-Wang liquidation",
    description=(
        "Closed-form Obizhaeva-Wang (2013) optimal liquidation under "
        "linear impact + finite resilience. Returns the discrete-"
        "continuous-discrete trade trajectory plus the cost sensitivity "
        "to the resilience parameter rho. Pairs with "
        "aqp.strategies.hft.obizhaeva_wang_exec.ObizhaevaWangExecution."
    ),
    params_model=OWLiquidationParams,
    requires_dataset=False,
    tags=("optimal_control", "execution", "obizhaeva_wang"),
    optional_dependencies=("jax", "jaxlib"),
)
def obizhaeva_wang_solve_flow(
    df: Any, params: OWLiquidationParams, ctx: FlowContext
) -> FlowResult:
    from aqp.optimal_control.obizhaeva_wang import (
        ObizhaevaWangParams,
        cost_vs_resilience,
        solve as solve_ow,
    )

    p = ObizhaevaWangParams(
        total_shares=params.total_shares,
        horizon=params.horizon,
        resilience=params.resilience,
        impact_coeff=params.impact_coeff,
        grid_points=params.grid_points,
    )
    result = solve_ow(p)
    rho_grid = np.linspace(
        params.rho_sweep_low, params.rho_sweep_high, params.rho_sweep_points
    )
    sweep = cost_vs_resilience(p, rho_grid=rho_grid)

    rows = []
    for t, executed in zip(result.times.tolist(), result.cumulative_executed.tolist()):
        rows.append({"t": float(t), "cumulative_executed": float(executed)})
    sweep_rows = [
        {"rho": float(r), "expected_cost": float(c)}
        for r, c in zip(sweep["rho"].tolist(), sweep["expected_cost"].tolist())
    ]

    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [r["t"] for r in rows],
                "y": [r["cumulative_executed"] for r in rows],
                "name": "cumulative executed",
            },
        ],
        "layout": {
            "title": "Obizhaeva-Wang optimal execution trajectory",
            "xaxis": {"title": "t"},
            "yaxis": {"title": "cumulative qty"},
        },
    }
    metrics = {
        "initial_chunk": float(result.initial_chunk),
        "terminal_chunk": float(result.terminal_chunk),
        "continuous_total": float(result.continuous_total),
        "continuous_rate": float(result.continuous_rate),
        "expected_cost": float(result.expected_cost),
        "rho_used": float(params.resilience),
    }
    return FlowResult(
        flow="optimal_control.obizhaeva_wang_solve",
        metrics=metrics,
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows + sweep_rows),
    )


__all__ = [
    "AvSTQuoteParams",
    "CJLiquidationParams",
    "LucicTseFlowParams",
    "OWLiquidationParams",
    "ToxicityRegimeParams",
    "avellaneda_stoikov_quotes_flow",
    "cartea_jaimungal_liquidation_flow",
    "lucic_tse_portfolio_quotes_flow",
    "obizhaeva_wang_solve_flow",
    "toxicity_regime_flow",
]
