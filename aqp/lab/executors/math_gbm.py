"""``math.gbm`` — Geometric Brownian Motion path simulator.

JAX-vmap-style API but uses numpy when JAX isn't available so the
executor stays importable in dev.

Params:

- ``S0`` (float, default 100.0).
- ``mu`` (float, default 0.05).
- ``sigma`` (float, default 0.2).
- ``T`` (float, default 1.0) — years.
- ``n_steps`` (int, default 252).
- ``n_paths`` (int, default 1000).
- ``seed`` (int, default 42).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from aqp.lab.executors._helpers import base_locator, stash_arrow_output
from aqp.lab.executors._types import NodeContext, NodeResult


def execute(node, ctx: NodeContext) -> NodeResult:
    params = dict(getattr(node, "params", {}) or {})
    S0 = float(params.get("S0") or 100.0)
    mu = float(params.get("mu") or 0.05)
    sigma = float(params.get("sigma") or 0.2)
    T = float(params.get("T") or 1.0)
    n_steps = int(params.get("n_steps") or 252)
    n_paths = int(params.get("n_paths") or 1000)
    seed = int(params.get("seed") or 42)

    dt = T / max(1, n_steps)
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((n_paths, n_steps))
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * Z
    log_returns = np.cumsum(drift + diffusion, axis=1)
    paths = S0 * np.exp(log_returns)
    paths = np.concatenate([np.full((n_paths, 1), S0), paths], axis=1)
    # Build a long-format DataFrame: (step, path_id) -> price.
    step_cols = [f"step_{i}" for i in range(paths.shape[1])]
    df = pd.DataFrame(paths, columns=step_cols)
    df.insert(0, "path_id", np.arange(n_paths))
    stash_arrow_output(ctx, node.id, df)
    return NodeResult(
        status="done",
        output_locator={
            **base_locator(node.id, df),
            "S0": S0,
            "mu": mu,
            "sigma": sigma,
            "T": T,
            "n_paths": n_paths,
            "seed": seed,
        },
        metrics={
            "mean_final": float(paths[:, -1].mean()),
            "std_final": float(paths[:, -1].std(ddof=1)),
            "n_paths": n_paths,
        },
        log_label=f"gbm:S0={S0} mu={mu} sigma={sigma} T={T}",
    )
