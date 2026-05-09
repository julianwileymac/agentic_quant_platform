"""Derivatives-pricing flows.

Calls :mod:`aqp.analysis.pricing` for the math; flows are thin
metadata-rich wrappers that the lab UI auto-renders.

Catalogue:

- ``derivatives.bsm`` — Black-Scholes-Merton call / put + Greeks.
- ``derivatives.greeks_surface`` — Δ/Γ/ν/Θ/ρ across strike × expiry.
- ``derivatives.implied_volatility`` — Brent-root solver for σ.
- ``derivatives.monte_carlo_european`` — vectorised GBM MC pricer.
- ``derivatives.monte_carlo_barrier`` — knock-in / knock-out variants.
- ``derivatives.monte_carlo_asian`` — arithmetic / geometric averaging.
- ``derivatives.sabr_smile`` — Hagan SABR implied-vol smile.
- ``derivatives.bachelier`` — wraps :mod:`aqp.options.normal_model`.
"""
from __future__ import annotations

import logging
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field

from aqp.analysis import pricing
from aqp.analysis.base import FlowContext, FlowParams, FlowResult, coerce_arrow
from aqp.analysis.registry import register_analysis_flow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Black-Scholes-Merton
# ---------------------------------------------------------------------------


class BSMParams(FlowParams):
    spot: float
    strike: float
    rate: float = 0.0
    vol: float = 0.2
    ttm: float = Field(..., gt=0.0, description="Time to maturity in years")
    option_type: Literal["call", "put"] = "call"
    dividend_yield: float = 0.0


@register_analysis_flow(
    name="derivatives.bsm",
    namespace="derivatives",
    label="Black-Scholes-Merton",
    description="Closed-form European option price + analytical Greeks.",
    params_model=BSMParams,
    requires_dataset=False,
    tags=("derivatives", "options"),
)
def bsm_flow(
    df: Any, params: BSMParams, ctx: FlowContext
) -> FlowResult:
    res = pricing.bsm_price(
        spot=params.spot,
        strike=params.strike,
        rate=params.rate,
        vol=params.vol,
        ttm=params.ttm,
        option_type=params.option_type,
        dividend_yield=params.dividend_yield,
    )
    metrics = res.to_dict()
    metrics.update(
        {
            "spot": float(params.spot),
            "strike": float(params.strike),
            "ttm": float(params.ttm),
            "vol": float(params.vol),
            "rate": float(params.rate),
            "option_type": params.option_type,
        }
    )
    return FlowResult(
        flow="derivatives.bsm",
        metrics=metrics,
        rows=[metrics],
    )


class GreeksSurfaceParams(FlowParams):
    spot: float
    strikes: list[float]
    expiries: list[float] = Field(..., description="Expiries in years")
    rate: float = 0.0
    vol: float = 0.2
    option_type: Literal["call", "put"] = "call"
    dividend_yield: float = 0.0


@register_analysis_flow(
    name="derivatives.greeks_surface",
    namespace="derivatives",
    label="Greeks surface",
    description="Δ/Γ/ν/Θ/ρ surface across strikes × expiries.",
    params_model=GreeksSurfaceParams,
    requires_dataset=False,
    tags=("derivatives", "greeks"),
)
def greeks_surface_flow(
    df: Any, params: GreeksSurfaceParams, ctx: FlowContext
) -> FlowResult:
    if not params.strikes or not params.expiries:
        return FlowResult(
            flow="derivatives.greeks_surface",
            error="strikes and expiries must be non-empty",
        )
    grid = pricing.greeks_grid(
        spot=params.spot,
        strikes=np.asarray(params.strikes, dtype=float),
        expiries=np.asarray(params.expiries, dtype=float),
        rate=params.rate,
        vol=params.vol,
        option_type=params.option_type,
        dividend_yield=params.dividend_yield,
    )
    rows: list[dict[str, Any]] = []
    for i, t in enumerate(params.expiries):
        for j, k in enumerate(params.strikes):
            rows.append(
                {
                    "expiry": float(t),
                    "strike": float(k),
                    "price": float(grid["price"][i, j]),
                    "delta": float(grid["delta"][i, j]),
                    "gamma": float(grid["gamma"][i, j]),
                    "vega": float(grid["vega"][i, j]),
                    "theta": float(grid["theta"][i, j]),
                    "rho": float(grid["rho"][i, j]),
                }
            )
    chart = {
        "data": [
            {
                "type": "heatmap",
                "x": list(map(float, params.strikes)),
                "y": list(map(float, params.expiries)),
                "z": grid["delta"].tolist(),
                "colorbar": {"title": "delta"},
                "name": "delta",
            }
        ],
        "layout": {
            "title": f"Delta surface ({params.option_type})",
            "xaxis": {"title": "strike"},
            "yaxis": {"title": "expiry"},
        },
    }
    return FlowResult(
        flow="derivatives.greeks_surface",
        metrics={
            "n_strikes": len(params.strikes),
            "n_expiries": len(params.expiries),
            "vol": float(params.vol),
            "rate": float(params.rate),
        },
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


class IVParams(FlowParams):
    market_price: float
    spot: float
    strike: float
    rate: float = 0.0
    ttm: float = Field(..., gt=0.0)
    option_type: Literal["call", "put"] = "call"
    dividend_yield: float = 0.0


@register_analysis_flow(
    name="derivatives.implied_volatility",
    namespace="derivatives",
    label="Implied volatility (Brent)",
    description="Brent root-find for σ such that BSM price matches market quote.",
    params_model=IVParams,
    requires_dataset=False,
    tags=("derivatives", "iv"),
)
def implied_vol_flow(
    df: Any, params: IVParams, ctx: FlowContext
) -> FlowResult:
    iv = pricing.bsm_implied_vol(
        market_price=params.market_price,
        spot=params.spot,
        strike=params.strike,
        rate=params.rate,
        ttm=params.ttm,
        option_type=params.option_type,
        dividend_yield=params.dividend_yield,
    )
    return FlowResult(
        flow="derivatives.implied_volatility",
        metrics={
            "implied_vol": float(iv) if iv == iv else None,  # NaN guard
            "market_price": float(params.market_price),
            "spot": float(params.spot),
            "strike": float(params.strike),
            "ttm": float(params.ttm),
            "option_type": params.option_type,
        },
    )


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------


class MCEuropeanParams(FlowParams):
    spot: float
    strike: float
    rate: float = 0.0
    vol: float = 0.2
    ttm: float = Field(..., gt=0.0)
    n_paths: int = Field(default=50_000, ge=100, le=2_000_000)
    n_steps: int = Field(default=50, ge=1, le=10_000)
    option_type: Literal["call", "put"] = "call"
    dividend_yield: float = 0.0
    seed: int | None = 42
    device: Literal["cpu", "cuda"] = "cpu"


@register_analysis_flow(
    name="derivatives.monte_carlo_european",
    namespace="derivatives",
    label="MC European option",
    description=(
        "Vectorised Geometric-Brownian-Motion Monte Carlo pricer. "
        "Optional CUDA path via cupy."
    ),
    params_model=MCEuropeanParams,
    requires_dataset=False,
    tags=("derivatives", "monte_carlo"),
)
def mc_european_flow(
    df: Any, params: MCEuropeanParams, ctx: FlowContext
) -> FlowResult:
    res = pricing.monte_carlo_european_price(
        spot=params.spot,
        strike=params.strike,
        rate=params.rate,
        vol=params.vol,
        ttm=params.ttm,
        n_paths=params.n_paths,
        n_steps=params.n_steps,
        option_type=params.option_type,
        dividend_yield=params.dividend_yield,
        seed=params.seed,
        device=params.device,
    )
    bsm = pricing.bsm_price(
        spot=params.spot,
        strike=params.strike,
        rate=params.rate,
        vol=params.vol,
        ttm=params.ttm,
        option_type=params.option_type,
        dividend_yield=params.dividend_yield,
    ).price
    return FlowResult(
        flow="derivatives.monte_carlo_european",
        metrics={
            **res,
            "bsm_reference": float(bsm),
            "absolute_error": float(abs(res["price"] - bsm)),
        },
    )


class MCBarrierParams(FlowParams):
    spot: float
    strike: float
    barrier: float
    rate: float = 0.0
    vol: float = 0.2
    ttm: float = Field(..., gt=0.0)
    n_paths: int = Field(default=50_000, ge=100, le=2_000_000)
    n_steps: int = Field(default=100, ge=10, le=10_000)
    option_type: Literal["call", "put"] = "call"
    barrier_type: Literal["up_in", "up_out", "down_in", "down_out"] = "up_out"
    dividend_yield: float = 0.0
    seed: int | None = 42


@register_analysis_flow(
    name="derivatives.monte_carlo_barrier",
    namespace="derivatives",
    label="MC barrier option",
    description="Path-dependent barrier option (knock-in / knock-out).",
    params_model=MCBarrierParams,
    requires_dataset=False,
    tags=("derivatives", "monte_carlo", "barrier"),
)
def mc_barrier_flow(
    df: Any, params: MCBarrierParams, ctx: FlowContext
) -> FlowResult:
    res = pricing.monte_carlo_barrier_price(
        spot=params.spot,
        strike=params.strike,
        barrier=params.barrier,
        rate=params.rate,
        vol=params.vol,
        ttm=params.ttm,
        n_paths=params.n_paths,
        n_steps=params.n_steps,
        option_type=params.option_type,
        barrier_type=params.barrier_type,
        dividend_yield=params.dividend_yield,
        seed=params.seed,
    )
    return FlowResult(
        flow="derivatives.monte_carlo_barrier",
        metrics={
            **res,
            "barrier": float(params.barrier),
            "barrier_type": params.barrier_type,
            "option_type": params.option_type,
        },
    )


class MCAsianParams(FlowParams):
    spot: float
    strike: float
    rate: float = 0.0
    vol: float = 0.2
    ttm: float = Field(..., gt=0.0)
    n_paths: int = Field(default=50_000, ge=100, le=2_000_000)
    n_steps: int = Field(default=100, ge=10, le=10_000)
    option_type: Literal["call", "put"] = "call"
    averaging: Literal["arithmetic", "geometric"] = "arithmetic"
    dividend_yield: float = 0.0
    seed: int | None = 42


@register_analysis_flow(
    name="derivatives.monte_carlo_asian",
    namespace="derivatives",
    label="MC Asian option",
    description="Path-dependent average-rate option (arithmetic or geometric).",
    params_model=MCAsianParams,
    requires_dataset=False,
    tags=("derivatives", "monte_carlo", "asian"),
)
def mc_asian_flow(
    df: Any, params: MCAsianParams, ctx: FlowContext
) -> FlowResult:
    res = pricing.monte_carlo_asian_price(
        spot=params.spot,
        strike=params.strike,
        rate=params.rate,
        vol=params.vol,
        ttm=params.ttm,
        n_paths=params.n_paths,
        n_steps=params.n_steps,
        option_type=params.option_type,
        averaging=params.averaging,
        dividend_yield=params.dividend_yield,
        seed=params.seed,
    )
    return FlowResult(
        flow="derivatives.monte_carlo_asian",
        metrics={**res, "averaging": params.averaging, "option_type": params.option_type},
    )


# ---------------------------------------------------------------------------
# SABR smile
# ---------------------------------------------------------------------------


class SABRParams(FlowParams):
    forward: float
    strikes: list[float]
    ttm: float = Field(..., gt=0.0)
    alpha: float = Field(default=0.2, gt=0.0)
    beta: float = Field(default=0.5, ge=0.0, le=1.0)
    rho: float = Field(default=0.0, ge=-1.0, le=1.0)
    nu: float = Field(default=0.4, gt=0.0)


@register_analysis_flow(
    name="derivatives.sabr_smile",
    namespace="derivatives",
    label="SABR smile (Hagan)",
    description="Hagan-Kumar-Lesniewski-Woodward 2002 lognormal-vol smile.",
    params_model=SABRParams,
    requires_dataset=False,
    tags=("derivatives", "sabr", "smile"),
)
def sabr_smile_flow(
    df: Any, params: SABRParams, ctx: FlowContext
) -> FlowResult:
    rows = []
    for k in params.strikes:
        iv = pricing.sabr_implied_vol(
            forward=params.forward,
            strike=float(k),
            ttm=params.ttm,
            alpha=params.alpha,
            beta=params.beta,
            rho=params.rho,
            nu=params.nu,
        )
        rows.append({"strike": float(k), "implied_vol": float(iv)})
    chart = {
        "data": [
            {
                "type": "scatter",
                "mode": "lines+markers",
                "x": [r["strike"] for r in rows],
                "y": [r["implied_vol"] for r in rows],
                "name": "SABR smile",
            }
        ],
        "layout": {
            "title": "SABR implied-volatility smile",
            "xaxis": {"title": "strike"},
            "yaxis": {"title": "implied vol"},
        },
    }
    return FlowResult(
        flow="derivatives.sabr_smile",
        metrics={
            "forward": float(params.forward),
            "ttm": float(params.ttm),
            "alpha": float(params.alpha),
            "beta": float(params.beta),
            "rho": float(params.rho),
            "nu": float(params.nu),
            "n_strikes": len(rows),
        },
        rows=rows,
        chart=chart,
        arrow_table=coerce_arrow(rows),
    )


# ---------------------------------------------------------------------------
# Bachelier (normal model) — wraps existing aqp.options.normal_model
# ---------------------------------------------------------------------------


class BachelierParams(FlowParams):
    spot: float
    strike: float
    rate: float = 0.0
    vol: float = 1.0
    ttm: float = Field(..., gt=0.0)
    option_type: Literal["call", "put"] = "call"


@register_analysis_flow(
    name="derivatives.bachelier",
    namespace="derivatives",
    label="Bachelier (normal model)",
    description=(
        "Bachelier 1900 'normal' option pricer. Wraps "
        "aqp.options.normal_model — vol is in absolute units, not log."
    ),
    params_model=BachelierParams,
    requires_dataset=False,
    tags=("derivatives", "bachelier"),
)
def bachelier_flow(
    df: Any, params: BachelierParams, ctx: FlowContext
) -> FlowResult:
    try:
        from aqp.options import normal_model
    except Exception as exc:  # pragma: no cover
        return FlowResult(flow="derivatives.bachelier", error=str(exc))
    fn_price = (
        getattr(normal_model, "bachelier_price", None)
        or getattr(normal_model, "price", None)
    )
    if fn_price is None:
        return FlowResult(
            flow="derivatives.bachelier",
            error="aqp.options.normal_model is missing a price function",
        )
    try:
        price = float(
            fn_price(
                spot=params.spot,
                strike=params.strike,
                rate=params.rate,
                vol=params.vol,
                ttm=params.ttm,
                option_type=params.option_type,
            )
        )
    except TypeError:
        # Some implementations use positional or differently-named args; try
        # the common alternative signature ``(F, K, T, sigma, option_type)``.
        try:
            price = float(
                fn_price(
                    params.spot,
                    params.strike,
                    params.ttm,
                    params.vol,
                    params.option_type,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return FlowResult(flow="derivatives.bachelier", error=str(exc))
    metrics = {
        "price": price,
        "spot": float(params.spot),
        "strike": float(params.strike),
        "ttm": float(params.ttm),
        "vol": float(params.vol),
        "rate": float(params.rate),
        "option_type": params.option_type,
    }
    return FlowResult(
        flow="derivatives.bachelier",
        metrics=metrics,
        rows=[metrics],
    )


_ = pd  # keep import in case future flows want pandas


__all__ = [
    "BachelierParams",
    "BSMParams",
    "GreeksSurfaceParams",
    "IVParams",
    "MCAsianParams",
    "MCBarrierParams",
    "MCEuropeanParams",
    "SABRParams",
    "bachelier_flow",
    "bsm_flow",
    "greeks_surface_flow",
    "implied_vol_flow",
    "mc_asian_flow",
    "mc_barrier_flow",
    "mc_european_flow",
    "sabr_smile_flow",
]
