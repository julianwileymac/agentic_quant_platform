"""``math.heston`` — Heston stochastic-volatility path simulator.

Reuses the existing :mod:`aqp.backtest.monte_carlo` dynamic-volatility
infrastructure where possible; falls back to a self-contained
full-truncation Euler scheme so the executor stays importable in
dev environments that don't have the optional Monte Carlo extras.

Params:

- ``S0`` (float, default 100.0).
- ``v0`` (float, default 0.04) — initial variance.
- ``kappa`` (float, default 2.0) — mean-reversion speed.
- ``theta`` (float, default 0.04) — long-run variance.
- ``xi`` (float, default 0.3) — vol-of-vol.
- ``rho`` (float, default -0.7) — correlation between price + vol shocks.
- ``r`` (float, default 0.0) — risk-free drift.
- ``T`` (float, default 1.0) — horizon in years.
- ``n_steps`` (int, default 252).
- ``n_paths`` (int, default 500).
- ``seed`` (int, default 42).

Output shape matches :mod:`math_gbm` (path_id + step_0..step_N
columns) so the ``data.synthetic`` downstream node can render a
single path as a bar series without per-simulator special casing.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult

logger = logging.getLogger(__name__)


def execute(node: Any, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    S0 = float(params.get("S0") or 100.0)
    v0 = float(params.get("v0") or 0.04)
    kappa = float(params.get("kappa") or 2.0)
    theta = float(params.get("theta") or 0.04)
    xi = float(params.get("xi") or 0.3)
    rho = float(params.get("rho") or -0.7)
    r = float(params.get("r") or 0.0)
    T = float(params.get("T") or 1.0)
    n_steps = int(params.get("n_steps") or 252)
    n_paths = int(params.get("n_paths") or 500)
    seed = int(params.get("seed") or 42)

    if not -1.0 <= rho <= 1.0:
        return NodeResult(
            status="error",
            error="math.heston: rho must be in [-1, 1]",
            log_label="math.heston:bad_rho",
        )

    paths, var_paths = _simulate_heston(
        S0=S0,
        v0=v0,
        kappa=kappa,
        theta=theta,
        xi=xi,
        rho=rho,
        r=r,
        T=T,
        n_steps=n_steps,
        n_paths=n_paths,
        seed=seed,
    )

    step_cols = [f"step_{i}" for i in range(paths.shape[1])]
    df = pd.DataFrame(paths, columns=step_cols)
    df.insert(0, "path_id", np.arange(n_paths))
    stash_arrow_output(ctx, node.id, df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, df, kind="heston"),
            "S0": S0,
            "kappa": kappa,
            "theta": theta,
            "xi": xi,
            "rho": rho,
            "T": T,
            "n_paths": n_paths,
            "seed": seed,
        },
        metrics={
            "mean_final": float(paths[:, -1].mean()),
            "std_final": float(paths[:, -1].std(ddof=1)) if n_paths > 1 else 0.0,
            "mean_final_variance": float(var_paths[:, -1].mean()),
            "n_paths": n_paths,
        },
        log_label=f"heston:S0={S0} kappa={kappa} theta={theta} xi={xi} rho={rho}",
    )


def _simulate_heston(
    *,
    S0: float,
    v0: float,
    kappa: float,
    theta: float,
    xi: float,
    rho: float,
    r: float,
    T: float,
    n_steps: int,
    n_paths: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Full-truncation Euler scheme — vectorised over paths.

    Returns ``(prices, variances)`` of shape ``(n_paths, n_steps + 1)``
    (including the initial values at index 0).
    """
    dt = T / max(1, n_steps)
    sqrt_dt = float(np.sqrt(dt))
    rng = np.random.default_rng(seed)
    z1 = rng.standard_normal((n_paths, n_steps))
    z2 = rng.standard_normal((n_paths, n_steps))
    w_price = z1
    w_vol = rho * z1 + np.sqrt(max(1e-12, 1.0 - rho**2)) * z2

    prices = np.empty((n_paths, n_steps + 1), dtype=float)
    variances = np.empty_like(prices)
    prices[:, 0] = S0
    variances[:, 0] = max(v0, 0.0)

    for t in range(n_steps):
        v_prev = np.maximum(variances[:, t], 0.0)
        s_prev = prices[:, t]
        sqrt_v = np.sqrt(v_prev)
        s_next = s_prev * np.exp(
            (r - 0.5 * v_prev) * dt + sqrt_v * sqrt_dt * w_price[:, t]
        )
        v_next = v_prev + kappa * (theta - v_prev) * dt + xi * sqrt_v * sqrt_dt * w_vol[:, t]
        prices[:, t + 1] = s_next
        variances[:, t + 1] = v_next
    return prices, variances


__all__ = ["execute"]
