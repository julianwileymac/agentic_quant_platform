"""``math.ou_jump`` — Ornstein-Uhlenbeck mean reversion + Poisson jumps.

Params:

- ``X0`` (float, default 0.0) — initial OU level.
- ``mu`` (float, default 0.0) — long-run mean (theta in standard OU
  notation).
- ``theta_speed`` (float, default 1.0) — mean-reversion speed.
- ``sigma`` (float, default 0.2) — OU diffusion volatility.
- ``jump_intensity`` (float, default 1.0) — Poisson rate per year.
- ``jump_mean`` (float, default 0.0) — jump size mean (lognormal-style).
- ``jump_std`` (float, default 0.05) — jump size std.
- ``T`` (float, default 1.0).
- ``n_steps`` (int, default 252).
- ``n_paths`` (int, default 500).
- ``seed`` (int, default 42).

Output frame shape matches :mod:`math_gbm` / :mod:`math_heston` so
the downstream ``data.synthetic`` consumer doesn't need
per-simulator special casing.
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
    X0 = float(params.get("X0") or 0.0)
    mu = float(params.get("mu") or 0.0)
    theta_speed = float(params.get("theta_speed") or 1.0)
    sigma = float(params.get("sigma") or 0.2)
    jump_intensity = float(params.get("jump_intensity") or 1.0)
    jump_mean = float(params.get("jump_mean") or 0.0)
    jump_std = float(params.get("jump_std") or 0.05)
    T = float(params.get("T") or 1.0)
    n_steps = int(params.get("n_steps") or 252)
    n_paths = int(params.get("n_paths") or 500)
    seed = int(params.get("seed") or 42)

    dt = T / max(1, n_steps)
    sqrt_dt = float(np.sqrt(dt))
    rng = np.random.default_rng(seed)
    diffusion_shocks = rng.standard_normal((n_paths, n_steps))
    # Poisson(λ·dt) jump count per (path, step)
    jump_counts = rng.poisson(lam=jump_intensity * dt, size=(n_paths, n_steps))
    jump_magnitudes = rng.normal(loc=jump_mean, scale=jump_std, size=(n_paths, n_steps))
    jumps = jump_counts.astype(float) * jump_magnitudes

    paths = np.empty((n_paths, n_steps + 1), dtype=float)
    paths[:, 0] = X0
    for t in range(n_steps):
        x_prev = paths[:, t]
        drift = theta_speed * (mu - x_prev) * dt
        diffusion = sigma * sqrt_dt * diffusion_shocks[:, t]
        paths[:, t + 1] = x_prev + drift + diffusion + jumps[:, t]

    step_cols = [f"step_{i}" for i in range(paths.shape[1])]
    df = pd.DataFrame(paths, columns=step_cols)
    df.insert(0, "path_id", np.arange(n_paths))
    stash_arrow_output(ctx, node.id, df)
    jump_total = int(jump_counts.sum())
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, df, kind="ou_jump"),
            "X0": X0,
            "mu": mu,
            "theta_speed": theta_speed,
            "sigma": sigma,
            "jump_intensity": jump_intensity,
            "jump_mean": jump_mean,
            "jump_std": jump_std,
            "T": T,
            "n_paths": n_paths,
            "seed": seed,
        },
        metrics={
            "mean_final": float(paths[:, -1].mean()),
            "std_final": float(paths[:, -1].std(ddof=1)) if n_paths > 1 else 0.0,
            "expected_jumps_per_path": float(jump_intensity * T),
            "observed_jumps_total": jump_total,
            "n_paths": n_paths,
        },
        log_label=f"ou_jump:mu={mu} sigma={sigma} lambda={jump_intensity}",
    )


__all__ = ["execute"]
