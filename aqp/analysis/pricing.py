"""Vectorised math primitives shared by the derivatives flow catalog.

We deliberately keep this module dependency-light (numpy + scipy.stats
only) so it imports cheaply during cold starts. GPU acceleration via
``cupy`` is opt-in and lives behind the
:func:`monte_carlo_gbm` ``device`` argument.

The Bachelier (normal) pricing path is hosted by
:mod:`aqp.options.normal_model`. Here we add the missing
Black-Scholes-Merton closed-form, the Greeks (analytical), and the
log-normal Monte Carlo paths that ``aqp.analysis.flows.derivatives``
wraps.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Black-Scholes-Merton
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class BSMResult:
    """Closed-form Black-Scholes-Merton call/put price + Greeks."""

    price: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    def to_dict(self) -> dict[str, float]:
        return {
            "price": float(self.price),
            "delta": float(self.delta),
            "gamma": float(self.gamma),
            "vega": float(self.vega),
            "theta": float(self.theta),
            "rho": float(self.rho),
        }


def bsm_d1(spot: float, strike: float, rate: float, vol: float, ttm: float, q: float = 0.0) -> float:
    """``d1`` from the Black-Scholes-Merton equation (continuous-yield variant)."""
    if vol <= 0 or ttm <= 0:
        return float("nan")
    return (
        math.log(spot / strike) + (rate - q + 0.5 * vol * vol) * ttm
    ) / (vol * math.sqrt(ttm))


def bsm_d2(spot: float, strike: float, rate: float, vol: float, ttm: float, q: float = 0.0) -> float:
    return bsm_d1(spot, strike, rate, vol, ttm, q) - vol * math.sqrt(ttm)


def bsm_price(
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    ttm: float,
    *,
    option_type: Literal["call", "put"] = "call",
    dividend_yield: float = 0.0,
) -> BSMResult:
    """Closed-form European option price + analytical Greeks.

    Parameters mirror the textbook contract:

    - ``spot``: underlying spot price ``S``.
    - ``strike``: option strike ``K``.
    - ``rate``: continuously-compounded risk-free rate ``r``.
    - ``vol``: implied volatility ``σ``.
    - ``ttm``: time to maturity in years.
    - ``dividend_yield``: continuous yield ``q``; equity-friendly.

    Greeks are returned in the conventional Black-Scholes scaling:
    delta unitless, gamma per ``S``, vega per 1.0 unit of vol (not per
    %), theta per year, rho per 1.0 unit of rate.
    """
    if ttm <= 0 or vol <= 0:
        # Intrinsic value at expiry; Greeks zero.
        if option_type == "call":
            price = max(spot - strike, 0.0)
        else:
            price = max(strike - spot, 0.0)
        return BSMResult(price=price, delta=0.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)

    d1 = bsm_d1(spot, strike, rate, vol, ttm, dividend_yield)
    d2 = d1 - vol * math.sqrt(ttm)
    pv_strike = strike * math.exp(-rate * ttm)
    pv_spot = spot * math.exp(-dividend_yield * ttm)
    sqrt_t = math.sqrt(ttm)

    if option_type == "call":
        price = pv_spot * norm.cdf(d1) - pv_strike * norm.cdf(d2)
        delta = math.exp(-dividend_yield * ttm) * norm.cdf(d1)
        rho = strike * ttm * math.exp(-rate * ttm) * norm.cdf(d2)
        theta = (
            -(pv_spot * norm.pdf(d1) * vol) / (2.0 * sqrt_t)
            - rate * pv_strike * norm.cdf(d2)
            + dividend_yield * pv_spot * norm.cdf(d1)
        )
    else:
        price = pv_strike * norm.cdf(-d2) - pv_spot * norm.cdf(-d1)
        delta = -math.exp(-dividend_yield * ttm) * norm.cdf(-d1)
        rho = -strike * ttm * math.exp(-rate * ttm) * norm.cdf(-d2)
        theta = (
            -(pv_spot * norm.pdf(d1) * vol) / (2.0 * sqrt_t)
            + rate * pv_strike * norm.cdf(-d2)
            - dividend_yield * pv_spot * norm.cdf(-d1)
        )
    gamma = (math.exp(-dividend_yield * ttm) * norm.pdf(d1)) / (spot * vol * sqrt_t)
    vega = pv_spot * norm.pdf(d1) * sqrt_t

    return BSMResult(price=price, delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def bsm_implied_vol(
    market_price: float,
    spot: float,
    strike: float,
    rate: float,
    ttm: float,
    *,
    option_type: Literal["call", "put"] = "call",
    dividend_yield: float = 0.0,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Brent root-find for implied vol given a market quote."""
    from scipy.optimize import brentq

    def f(sigma: float) -> float:
        return (
            bsm_price(
                spot=spot,
                strike=strike,
                rate=rate,
                vol=max(sigma, 1e-6),
                ttm=ttm,
                option_type=option_type,
                dividend_yield=dividend_yield,
            ).price
            - market_price
        )

    try:
        return float(brentq(f, 1e-4, 5.0, xtol=tol, maxiter=max_iter))
    except Exception:  # noqa: BLE001
        return float("nan")


# ---------------------------------------------------------------------------
# Greeks across a strike x expiry surface
# ---------------------------------------------------------------------------


def greeks_grid(
    spot: float,
    strikes: np.ndarray,
    expiries: np.ndarray,
    *,
    rate: float = 0.0,
    vol: float = 0.2,
    option_type: Literal["call", "put"] = "call",
    dividend_yield: float = 0.0,
    use_jax: bool | None = None,
) -> dict[str, np.ndarray]:
    """Build a 2D Greek surface across ``(strike, expiry)``.

    Returns a dict with arrays of shape ``(len(expiries), len(strikes))``
    keyed ``price``, ``delta``, ``gamma``, ``vega``, ``theta``, ``rho``.

    Auto-routes through the JAX/fast-vollib fast path in
    :func:`aqp.options.greeks_jax.greeks_grid_jax` when the
    ``optimal-control`` extra is installed; falls back to this scipy
    double-loop otherwise. Pass ``use_jax=False`` to force the scipy
    path (mostly useful in tests).
    """
    if use_jax is not False:
        try:
            from aqp.options.greeks_jax import greeks_grid_jax
        except Exception:  # noqa: BLE001
            greeks_grid_jax = None  # type: ignore[assignment]
        if greeks_grid_jax is not None:
            jax_out = greeks_grid_jax(
                spot=spot,
                strikes=np.asarray(strikes, dtype=float),
                expiries=np.asarray(expiries, dtype=float),
                rate=rate,
                vol=vol,
                option_type=option_type,
                dividend_yield=dividend_yield,
            )
            if jax_out is not None:
                return jax_out

    K = np.asarray(strikes, dtype=float).reshape(1, -1)
    T = np.asarray(expiries, dtype=float).reshape(-1, 1)
    out_shape = (T.size, K.size)
    out = {
        "price": np.zeros(out_shape, dtype=float),
        "delta": np.zeros(out_shape, dtype=float),
        "gamma": np.zeros(out_shape, dtype=float),
        "vega": np.zeros(out_shape, dtype=float),
        "theta": np.zeros(out_shape, dtype=float),
        "rho": np.zeros(out_shape, dtype=float),
    }
    for i, ttm in enumerate(T.ravel()):
        for j, strike in enumerate(K.ravel()):
            res = bsm_price(
                spot=spot,
                strike=float(strike),
                rate=rate,
                vol=vol,
                ttm=float(ttm),
                option_type=option_type,
                dividend_yield=dividend_yield,
            )
            out["price"][i, j] = res.price
            out["delta"][i, j] = res.delta
            out["gamma"][i, j] = res.gamma
            out["vega"][i, j] = res.vega
            out["theta"][i, j] = res.theta
            out["rho"][i, j] = res.rho
    return out


# ---------------------------------------------------------------------------
# Monte Carlo GBM
# ---------------------------------------------------------------------------


def monte_carlo_gbm_paths(
    *,
    spot: float,
    rate: float,
    vol: float,
    ttm: float,
    n_paths: int,
    n_steps: int,
    dividend_yield: float = 0.0,
    seed: int | None = None,
    device: Literal["cpu", "cuda"] = "cpu",
) -> np.ndarray:
    """Simulate ``n_paths`` Geometric-Brownian-Motion paths.

    Returns an ``(n_paths, n_steps + 1)`` ndarray with ``S_0 = spot`` in
    the first column. ``device="cuda"`` opt-in routes through ``cupy``
    when installed; absent or import-error falls back to numpy with a
    single ``logger.debug``.
    """
    n_paths = max(int(n_paths), 1)
    n_steps = max(int(n_steps), 1)
    dt = float(ttm) / n_steps
    drift = (rate - dividend_yield - 0.5 * vol * vol) * dt
    diffusion = vol * math.sqrt(dt)

    use_gpu = device == "cuda"
    if use_gpu:
        try:
            import cupy as cp  # type: ignore[import-not-found]

            rng = cp.random.default_rng(seed)
            shocks = rng.standard_normal((n_paths, n_steps))
            log_paths = cp.cumsum(drift + diffusion * shocks, axis=1)
            paths = cp.empty((n_paths, n_steps + 1), dtype=cp.float64)
            paths[:, 0] = spot
            paths[:, 1:] = spot * cp.exp(log_paths)
            return cp.asnumpy(paths)
        except Exception:  # noqa: BLE001
            logger.debug("cupy GPU MC unavailable, falling back to numpy")

    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((n_paths, n_steps))
    log_paths = np.cumsum(drift + diffusion * shocks, axis=1)
    paths = np.empty((n_paths, n_steps + 1), dtype=np.float64)
    paths[:, 0] = spot
    paths[:, 1:] = spot * np.exp(log_paths)
    return paths


def monte_carlo_european_price(
    *,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    ttm: float,
    n_paths: int = 50_000,
    n_steps: int = 50,
    option_type: Literal["call", "put"] = "call",
    dividend_yield: float = 0.0,
    seed: int | None = None,
    device: Literal["cpu", "cuda"] = "cpu",
) -> dict[str, float]:
    """MC price for a European option (terminal-payoff only).

    Returns ``{price, std_error, n_paths}``.
    """
    paths = monte_carlo_gbm_paths(
        spot=spot,
        rate=rate,
        vol=vol,
        ttm=ttm,
        n_paths=n_paths,
        n_steps=n_steps,
        dividend_yield=dividend_yield,
        seed=seed,
        device=device,
    )
    terminal = paths[:, -1]
    if option_type == "call":
        payoff = np.maximum(terminal - strike, 0.0)
    else:
        payoff = np.maximum(strike - terminal, 0.0)
    discount = math.exp(-rate * ttm)
    discounted = discount * payoff
    return {
        "price": float(discounted.mean()),
        "std_error": float(discounted.std(ddof=1) / math.sqrt(len(discounted))),
        "n_paths": int(len(discounted)),
    }


def monte_carlo_barrier_price(
    *,
    spot: float,
    strike: float,
    barrier: float,
    rate: float,
    vol: float,
    ttm: float,
    n_paths: int = 50_000,
    n_steps: int = 50,
    option_type: Literal["call", "put"] = "call",
    barrier_type: Literal["up_in", "up_out", "down_in", "down_out"] = "up_out",
    dividend_yield: float = 0.0,
    seed: int | None = None,
) -> dict[str, float]:
    paths = monte_carlo_gbm_paths(
        spot=spot,
        rate=rate,
        vol=vol,
        ttm=ttm,
        n_paths=n_paths,
        n_steps=n_steps,
        dividend_yield=dividend_yield,
        seed=seed,
    )
    if barrier_type.startswith("up"):
        hit = np.any(paths >= barrier, axis=1)
    else:
        hit = np.any(paths <= barrier, axis=1)
    knocked_in = barrier_type.endswith("in")
    if knocked_in:
        active = hit
    else:
        active = ~hit
    terminal = paths[:, -1]
    if option_type == "call":
        payoff = np.maximum(terminal - strike, 0.0)
    else:
        payoff = np.maximum(strike - terminal, 0.0)
    payoff = np.where(active, payoff, 0.0)
    discount = math.exp(-rate * ttm)
    discounted = discount * payoff
    return {
        "price": float(discounted.mean()),
        "std_error": float(discounted.std(ddof=1) / math.sqrt(len(discounted))),
        "n_paths": int(len(discounted)),
        "knock_probability": float(hit.mean()),
    }


def monte_carlo_asian_price(
    *,
    spot: float,
    strike: float,
    rate: float,
    vol: float,
    ttm: float,
    n_paths: int = 50_000,
    n_steps: int = 50,
    option_type: Literal["call", "put"] = "call",
    averaging: Literal["arithmetic", "geometric"] = "arithmetic",
    dividend_yield: float = 0.0,
    seed: int | None = None,
) -> dict[str, float]:
    paths = monte_carlo_gbm_paths(
        spot=spot,
        rate=rate,
        vol=vol,
        ttm=ttm,
        n_paths=n_paths,
        n_steps=n_steps,
        dividend_yield=dividend_yield,
        seed=seed,
    )
    if averaging == "arithmetic":
        avg = paths[:, 1:].mean(axis=1)
    else:  # geometric
        avg = np.exp(np.log(paths[:, 1:]).mean(axis=1))
    if option_type == "call":
        payoff = np.maximum(avg - strike, 0.0)
    else:
        payoff = np.maximum(strike - avg, 0.0)
    discount = math.exp(-rate * ttm)
    discounted = discount * payoff
    return {
        "price": float(discounted.mean()),
        "std_error": float(discounted.std(ddof=1) / math.sqrt(len(discounted))),
        "n_paths": int(len(discounted)),
    }


# ---------------------------------------------------------------------------
# SABR (Hagan 2002 lognormal-vol approximation)
# ---------------------------------------------------------------------------


def sabr_implied_vol(
    *,
    forward: float,
    strike: float,
    ttm: float,
    alpha: float,
    beta: float,
    rho: float,
    nu: float,
) -> float:
    """Hagan-style SABR lognormal implied volatility.

    See Hagan, Kumar, Lesniewski, Woodward (2002), eq. 2.17a/b. Used by
    the ``derivatives.sabr_smile`` flow to fit volatility smiles. We
    keep it standalone (no scipy) because the function gets called in
    a tight loop during calibration.
    """
    forward = max(float(forward), 1e-12)
    strike = max(float(strike), 1e-12)
    ttm = max(float(ttm), 1e-12)
    alpha = max(float(alpha), 1e-12)
    nu = max(float(nu), 1e-12)
    one_minus_beta = 1.0 - float(beta)

    if abs(forward - strike) < 1e-12:
        a = alpha / (forward ** one_minus_beta)
        first = a
        bb = (one_minus_beta * one_minus_beta) * (alpha * alpha)
        bb /= 24.0 * (forward ** (2.0 * one_minus_beta))
        cc = 0.25 * rho * beta * nu * alpha
        cc /= forward ** one_minus_beta
        dd = (2.0 - 3.0 * rho * rho) * nu * nu / 24.0
        return float(first * (1.0 + (bb + cc + dd) * ttm))

    log_fk = math.log(forward / strike)
    z = (nu / alpha) * ((forward * strike) ** (one_minus_beta / 2.0)) * log_fk
    chi = math.log(
        (math.sqrt(1.0 - 2.0 * rho * z + z * z) + z - rho) / (1.0 - rho)
    )
    base = alpha
    base /= (forward * strike) ** (one_minus_beta / 2.0)
    series = 1.0 + ((one_minus_beta * one_minus_beta) / 24.0) * (log_fk * log_fk)
    series += ((one_minus_beta ** 4) / 1920.0) * (log_fk ** 4)
    base /= series
    base *= z / chi
    factor = 1.0 + (
        ((one_minus_beta * one_minus_beta) / 24.0)
        * (alpha * alpha)
        / ((forward * strike) ** one_minus_beta)
        + 0.25 * rho * beta * nu * alpha
        / ((forward * strike) ** (one_minus_beta / 2.0))
        + (2.0 - 3.0 * rho * rho) * nu * nu / 24.0
    ) * ttm
    return float(base * factor)


__all__ = [
    "BSMResult",
    "bsm_d1",
    "bsm_d2",
    "bsm_implied_vol",
    "bsm_price",
    "greeks_grid",
    "monte_carlo_asian_price",
    "monte_carlo_barrier_price",
    "monte_carlo_european_price",
    "monte_carlo_gbm_paths",
    "sabr_implied_vol",
]
