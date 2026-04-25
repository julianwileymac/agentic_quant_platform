"""Monte Carlo — resample trade returns to stress-test robustness.

Four simulator families covered:

- :func:`run_monte_carlo` — bootstrap / parametric resampling of the
  equity curve (existing API, unchanged).
- :func:`simulate_drift` — GBM Monte Carlo with constant drift / sigma.
- :func:`simulate_dynamic_volatility` — EWMA-updated volatility, optional
  regime shifts.
- :func:`simulate_multivariate_drift` — correlated GBM across many
  symbols using a Cholesky decomposition of the empirical cov.
"""
from __future__ import annotations

import logging
from typing import Any, Sequence

import numpy as np
import pandas as pd

from aqp.backtest.metrics import max_drawdown, sharpe_ratio, sortino_ratio

logger = logging.getLogger(__name__)


def run_monte_carlo(
    equity_curve: pd.Series,
    n_runs: int = 500,
    method: str = "bootstrap",
    seed: int | None = 42,
) -> dict[str, Any]:
    """Resample daily returns to generate synthetic equity paths."""
    if equity_curve.empty:
        return {"n_runs": 0, "error": "empty equity curve"}
    rng = np.random.default_rng(seed)
    returns = equity_curve.pct_change().dropna().values
    initial = float(equity_curve.iloc[0])

    sharpes, sortinos, mdds, totals = [], [], [], []
    for _ in range(n_runs):
        if method == "bootstrap":
            sampled = rng.choice(returns, size=len(returns), replace=True)
        elif method == "parametric":
            sampled = rng.normal(returns.mean(), returns.std(ddof=0), size=len(returns))
        else:
            raise ValueError(f"Unknown method {method!r}")
        eq = pd.Series(initial * (1 + pd.Series(sampled)).cumprod().values)
        ret_s = pd.Series(sampled)
        sharpes.append(sharpe_ratio(ret_s))
        sortinos.append(sortino_ratio(ret_s))
        mdds.append(max_drawdown(eq))
        totals.append(float(eq.iloc[-1] / eq.iloc[0] - 1))

    def _pct(values):
        arr = np.asarray(values)
        return {
            "mean": float(arr.mean()),
            "median": float(np.median(arr)),
            "p05": float(np.percentile(arr, 5)),
            "p25": float(np.percentile(arr, 25)),
            "p75": float(np.percentile(arr, 75)),
            "p95": float(np.percentile(arr, 95)),
        }

    return {
        "n_runs": n_runs,
        "method": method,
        "sharpe": _pct(sharpes),
        "sortino": _pct(sortinos),
        "max_drawdown": _pct(mdds),
        "total_return": _pct(totals),
    }


# ---------------------------------------------------------------------------
# Forward simulators — synthesize future paths (not resamples of the past).
# ---------------------------------------------------------------------------


def simulate_drift(
    s0: float,
    mu: float,
    sigma: float,
    n_steps: int,
    n_paths: int = 1_000,
    dt: float = 1.0 / 252.0,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Geometric Brownian Motion Monte Carlo.

    Returns a ``(n_steps + 1, n_paths)`` frame of price paths.
    """
    rng = np.random.default_rng(seed)
    log_returns = (mu - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * rng.standard_normal((n_steps, n_paths))
    cum = log_returns.cumsum(axis=0)
    prices = np.vstack([np.full((1, n_paths), np.log(s0)), np.log(s0) + cum])
    return pd.DataFrame(np.exp(prices))


def simulate_dynamic_volatility(
    s0: float,
    mu: float,
    sigma_initial: float,
    n_steps: int,
    n_paths: int = 1_000,
    ewma_lambda: float = 0.94,
    shock_every: int | None = None,
    shock_scale: float = 2.0,
    dt: float = 1.0 / 252.0,
    seed: int | None = 42,
) -> pd.DataFrame:
    """GBM with EWMA-updated volatility and optional periodic shocks."""
    rng = np.random.default_rng(seed)
    prices = np.full((n_steps + 1, n_paths), float(s0))
    sigma = np.full(n_paths, float(sigma_initial))
    for t in range(1, n_steps + 1):
        z = rng.standard_normal(n_paths)
        realised = sigma * np.sqrt(dt) * z
        prices[t] = prices[t - 1] * np.exp((mu - 0.5 * sigma**2) * dt + realised)
        sigma = np.sqrt(ewma_lambda * sigma**2 + (1 - ewma_lambda) * (realised / np.sqrt(dt)) ** 2)
        if shock_every is not None and t % shock_every == 0:
            sigma = sigma * float(shock_scale)
    return pd.DataFrame(prices)


def simulate_multivariate_drift(
    prices: pd.DataFrame,
    n_steps: int,
    n_paths: int = 500,
    dt: float = 1.0 / 252.0,
    seed: int | None = 42,
) -> dict[str, pd.DataFrame]:
    """Correlated GBM across the columns of ``prices``.

    Estimates ``mu`` and ``cov`` from the log-return history, then
    simulates ``n_paths`` correlated price paths per symbol using the
    Cholesky factor of the covariance.
    """
    rng = np.random.default_rng(seed)
    log_ret = np.log(prices).diff().dropna()
    if log_ret.empty:
        raise ValueError("simulate_multivariate_drift: input prices are degenerate.")
    mu = log_ret.mean().values / dt
    sigma = log_ret.cov().values / dt
    try:
        L = np.linalg.cholesky(sigma)
    except np.linalg.LinAlgError:
        L = np.linalg.cholesky(sigma + 1e-6 * np.eye(sigma.shape[0]))

    d = mu.shape[0]
    s0 = prices.iloc[-1].values
    out = {col: np.full((n_steps + 1, n_paths), s0[i]) for i, col in enumerate(prices.columns)}
    for step in range(1, n_steps + 1):
        z = rng.standard_normal((n_paths, d))
        shocks = z @ L.T * np.sqrt(dt)
        for i, col in enumerate(prices.columns):
            prev = out[col][step - 1]
            out[col][step] = prev * np.exp((mu[i] - 0.5 * sigma[i, i]) * dt + shocks[:, i])
    return {col: pd.DataFrame(arr) for col, arr in out.items()}


def portfolio_return_percentiles(
    price_paths: dict[str, pd.DataFrame] | pd.DataFrame,
    weights: Sequence[float] | None = None,
    percentiles: Sequence[float] = (5, 25, 50, 75, 95),
) -> pd.DataFrame:
    """Summarise a simulation's terminal portfolio return distribution."""
    if isinstance(price_paths, pd.DataFrame):
        price_paths = {"asset": price_paths}
    syms = list(price_paths)
    if weights is None:
        weights = [1.0 / len(syms)] * len(syms)

    finals = []
    initials = []
    for sym, frame in price_paths.items():
        finals.append(frame.iloc[-1].values)
        initials.append(float(frame.iloc[0, 0]))
    finals = np.stack(finals)  # (n_assets, n_paths)
    initials_arr = np.asarray(initials)
    rets = (finals.T / initials_arr) - 1.0  # (n_paths, n_assets)
    port_rets = rets @ np.asarray(weights)
    return pd.DataFrame(
        {
            "percentile": list(percentiles),
            "terminal_return": [float(np.percentile(port_rets, p)) for p in percentiles],
        }
    ).set_index("percentile")


__all__ = [
    "portfolio_return_percentiles",
    "run_monte_carlo",
    "simulate_drift",
    "simulate_dynamic_volatility",
    "simulate_multivariate_drift",
]
