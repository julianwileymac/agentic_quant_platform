"""Bachelier (normal) model — closed-form prices and Greeks.

Used for low-priced underlyings where the lognormal assumption fails
(e.g. interest rates, basis spreads, near-zero commodity prices).

Source: ``inspiration/notebooks-master/Greeks_under_normal_model.ipynb``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BachelierGreeks:
    price: float
    delta: float
    gamma: float
    theta: float
    vega: float
    vanna: float
    volga: float
    veta: float


def _d(F: float, K: float, T: float, sigma: float) -> float:
    return (F - K) / (sigma * np.sqrt(T))


def bachelier_price(F: float, K: float, T: float, sigma: float, is_call: bool = True) -> float:
    """Bachelier price for European call/put on forward ``F``.

    Underlying assumed to follow ``dF = sigma dW`` (additive normal).
    Discounting is omitted (caller multiplies by ``exp(-rT)`` if needed).
    """
    if T <= 0 or sigma <= 0:
        intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
        return float(intrinsic)
    d = _d(F, K, T, sigma)
    sign = 1.0 if is_call else -1.0
    return float(sign * (F - K) * norm.cdf(sign * d) + sigma * np.sqrt(T) * norm.pdf(d))


def bachelier_greeks(F: float, K: float, T: float, sigma: float, is_call: bool = True) -> BachelierGreeks:
    """All standard Bachelier Greeks plus vanna, volga, veta.

    Greeks are dollar values per 1 unit move in the relevant variable.
    """
    if T <= 0 or sigma <= 0:
        intrinsic = max(F - K, 0.0) if is_call else max(K - F, 0.0)
        return BachelierGreeks(price=intrinsic, delta=0.0, gamma=0.0, theta=0.0, vega=0.0, vanna=0.0, volga=0.0, veta=0.0)
    d = _d(F, K, T, sigma)
    sign = 1.0 if is_call else -1.0
    sqrt_T = np.sqrt(T)
    pdf_d = norm.pdf(d)
    cdf_d = norm.cdf(sign * d)

    price = sign * (F - K) * cdf_d + sigma * sqrt_T * pdf_d
    delta = sign * cdf_d
    gamma = pdf_d / (sigma * sqrt_T)
    theta = -sigma * pdf_d / (2.0 * sqrt_T)
    vega = sqrt_T * pdf_d
    # vanna = d^2 V / (dF dsigma) = -d * pdf(d) / sigma * (...) — Bachelier closed form:
    vanna = -d * pdf_d / sigma
    # volga = d^2 V / dsigma^2 = sqrt(T) * pdf(d) * (d^2 / sigma)
    volga = sqrt_T * pdf_d * (d ** 2) / sigma
    # veta = d^2 V / (dT dsigma) = -pdf(d) / (2 * sqrt(T)) * (1 - d^2)
    veta = -pdf_d / (2.0 * sqrt_T) * (1.0 - d ** 2)
    return BachelierGreeks(
        price=float(price),
        delta=float(delta),
        gamma=float(gamma),
        theta=float(theta),
        vega=float(vega),
        vanna=float(vanna),
        volga=float(volga),
        veta=float(veta),
    )


def implied_normal_vol(
    target_price: float,
    F: float,
    K: float,
    T: float,
    is_call: bool = True,
    sigma_lo: float = 1e-6,
    sigma_hi: float = 100.0,
    tol: float = 1e-8,
) -> float:
    """Newton-bisect implied normal vol matching ``target_price``."""
    from scipy.optimize import brentq

    def f(s: float) -> float:
        return bachelier_price(F, K, T, s, is_call) - target_price

    try:
        return float(brentq(f, sigma_lo, sigma_hi, xtol=tol))
    except ValueError:
        return float("nan")


__all__ = [
    "BachelierGreeks",
    "bachelier_greeks",
    "bachelier_price",
    "implied_normal_vol",
]
