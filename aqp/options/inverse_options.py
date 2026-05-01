"""Inverse option analytics (Deribit-style).

Inverse options are settled in the underlying asset (e.g. BTC) rather
than quote currency (USD). PV and Greeks differ from vanilla.

Source: ``inspiration/notebooks-master/inverse_option.ipynb``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InverseGreeks:
    price_btc: float
    price_usd: float
    delta_usd: float
    gamma_usd: float
    vega: float
    theta: float


def _bs_d1_d2(F: float, K: float, T: float, sigma: float) -> tuple[float, float]:
    if T <= 0 or sigma <= 0:
        return float("nan"), float("nan")
    d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def inverse_call_price_btc(F: float, K: float, T: float, sigma: float) -> float:
    """Inverse call price expressed in BTC.

    Formula (Alexander 2022): ``C_BTC = (1/F) * BS_call(F, K, T, sigma)``
    where ``BS_call`` is the standard Black-76 call. The inverse contract
    is essentially long a vanilla call but settled in the underlying.
    """
    if T <= 0 or sigma <= 0:
        intrinsic = max(F - K, 0.0)
        return float(intrinsic / F if F > 0 else 0.0)
    d1, d2 = _bs_d1_d2(F, K, T, sigma)
    bs_call = F * norm.cdf(d1) - K * norm.cdf(d2)
    return float(bs_call / F)


def inverse_put_price_btc(F: float, K: float, T: float, sigma: float) -> float:
    """Inverse put price in BTC."""
    if T <= 0 or sigma <= 0:
        intrinsic = max(K - F, 0.0)
        return float(intrinsic / F if F > 0 else 0.0)
    d1, d2 = _bs_d1_d2(F, K, T, sigma)
    bs_put = K * norm.cdf(-d2) - F * norm.cdf(-d1)
    return float(bs_put / F)


def inverse_greeks(
    F: float,
    K: float,
    T: float,
    sigma: float,
    is_call: bool = True,
) -> InverseGreeks:
    """Inverse-option Greeks expressed in USD per 1 BTC move (delta) etc."""
    if T <= 0 or sigma <= 0:
        intrinsic = (max(F - K, 0.0) if is_call else max(K - F, 0.0))
        return InverseGreeks(
            price_btc=intrinsic / F if F > 0 else 0.0,
            price_usd=intrinsic,
            delta_usd=0.0, gamma_usd=0.0, vega=0.0, theta=0.0,
        )
    d1, d2 = _bs_d1_d2(F, K, T, sigma)
    sign = 1.0 if is_call else -1.0
    cdf_d1 = norm.cdf(sign * d1)
    pdf_d1 = norm.pdf(d1)

    bs_price = sign * (F * norm.cdf(sign * d1) - K * norm.cdf(sign * d2))
    price_usd = bs_price
    price_btc = bs_price / F

    # Inverse delta (USD/BTC): d(C_USD)/dF = standard delta = sign * cdf(sign*d1)
    delta_usd = sign * cdf_d1
    # Inverse gamma in USD: pdf(d1) / (F * sigma * sqrt(T))
    gamma_usd = pdf_d1 / (F * sigma * np.sqrt(T))
    # Vega: F * pdf(d1) * sqrt(T)  (per 1 vol point)
    vega = F * pdf_d1 * np.sqrt(T)
    # Theta: -F * pdf(d1) * sigma / (2*sqrt(T))
    theta = -F * pdf_d1 * sigma / (2.0 * np.sqrt(T))

    return InverseGreeks(
        price_btc=float(price_btc),
        price_usd=float(price_usd),
        delta_usd=float(delta_usd),
        gamma_usd=float(gamma_usd),
        vega=float(vega),
        theta=float(theta),
    )


def implied_vol_inverse(
    target_price_btc: float,
    F: float,
    K: float,
    T: float,
    is_call: bool = True,
    sigma_lo: float = 1e-4,
    sigma_hi: float = 5.0,
) -> float:
    """Implied vol from an inverse-option BTC price."""
    from scipy.optimize import brentq

    pricer = inverse_call_price_btc if is_call else inverse_put_price_btc

    def f(s: float) -> float:
        return pricer(F, K, T, s) - target_price_btc

    try:
        return float(brentq(f, sigma_lo, sigma_hi, xtol=1e-8))
    except ValueError:
        return float("nan")


__all__ = [
    "InverseGreeks",
    "implied_vol_inverse",
    "inverse_call_price_btc",
    "inverse_greeks",
    "inverse_put_price_btc",
]
