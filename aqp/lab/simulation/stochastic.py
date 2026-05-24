"""Stochastic sub-mode runner — vectorised path simulators.

Phase 4 wires the four canonical math processes onto Simulation mode:

- ``process='gbm'`` — Geometric Brownian Motion.
- ``process='heston'`` — Heston stochastic volatility.
- ``process='ou_jump'`` — Ornstein-Uhlenbeck mean reversion + Poisson jumps.
- ``process='regime_hmm'`` — Two-regime mixture (high-vol / low-vol).

Heavy work happens inside the underlying executor kernels (see
:mod:`aqp.lab.executors.math_heston` / :mod:`aqp.lab.executors.math_ou_jump`).
The runner just dispatches by name + aggregates summary metrics so
the Simulation panel renders a uniform shape regardless of process.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _gbm_paths(
    *,
    S0: float,
    mu: float,
    sigma: float,
    T: float,
    n_steps: int,
    n_paths: int,
    seed: int,
) -> np.ndarray:
    dt = T / max(1, n_steps)
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal((n_paths, n_steps))
    drift = (mu - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * Z
    log_returns = np.cumsum(drift + diffusion, axis=1)
    paths = S0 * np.exp(log_returns)
    return np.concatenate([np.full((n_paths, 1), S0), paths], axis=1)


def _heston_paths(
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
) -> np.ndarray:
    from aqp.lab.executors.math_heston import _simulate_heston

    prices, _variances = _simulate_heston(
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
    return prices


def _ou_jump_paths(
    *,
    X0: float,
    mu: float,
    theta_speed: float,
    sigma: float,
    jump_intensity: float,
    jump_mean: float,
    jump_std: float,
    T: float,
    n_steps: int,
    n_paths: int,
    seed: int,
) -> np.ndarray:
    dt = T / max(1, n_steps)
    sqrt_dt = float(np.sqrt(dt))
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((n_paths, n_steps))
    jump_counts = rng.poisson(lam=jump_intensity * dt, size=(n_paths, n_steps))
    jump_mags = rng.normal(loc=jump_mean, scale=jump_std, size=(n_paths, n_steps))
    jumps = jump_counts.astype(float) * jump_mags
    paths = np.empty((n_paths, n_steps + 1), dtype=float)
    paths[:, 0] = X0
    for t in range(n_steps):
        paths[:, t + 1] = (
            paths[:, t]
            + theta_speed * (mu - paths[:, t]) * dt
            + sigma * sqrt_dt * shocks[:, t]
            + jumps[:, t]
        )
    return paths


def _regime_hmm_paths(
    *,
    S0: float,
    mu_high: float,
    mu_low: float,
    sigma_high: float,
    sigma_low: float,
    transition_high_to_low: float,
    transition_low_to_high: float,
    T: float,
    n_steps: int,
    n_paths: int,
    seed: int,
) -> np.ndarray:
    """Two-state regime-switching log-normal returns."""
    dt = T / max(1, n_steps)
    sqrt_dt = float(np.sqrt(dt))
    rng = np.random.default_rng(seed)
    states = np.zeros((n_paths, n_steps + 1), dtype=int)  # 0 = high, 1 = low
    paths = np.empty_like(states, dtype=float)
    paths[:, 0] = S0
    for t in range(n_steps):
        prev_state = states[:, t]
        toss = rng.random(n_paths)
        # transition_high_to_low: chance of leaving high state.
        # transition_low_to_high: chance of leaving low state.
        next_state = prev_state.copy()
        high_mask = prev_state == 0
        low_mask = prev_state == 1
        next_state[high_mask] = np.where(
            toss[high_mask] < transition_high_to_low, 1, 0
        )
        next_state[low_mask] = np.where(
            toss[low_mask] < transition_low_to_high, 0, 1
        )
        states[:, t + 1] = next_state
        mu = np.where(prev_state == 0, mu_high, mu_low)
        sigma = np.where(prev_state == 0, sigma_high, sigma_low)
        z = rng.standard_normal(n_paths)
        paths[:, t + 1] = paths[:, t] * np.exp(
            (mu - 0.5 * sigma**2) * dt + sigma * sqrt_dt * z
        )
    return paths


def run_stochastic_simulation(
    payload: dict[str, Any], runtime: Any = None
) -> dict[str, Any]:
    started = time.time()
    extras = payload.get("extras") or {}
    process = str(extras.get("process") or "gbm").lower()
    n_paths = int(extras.get("n_paths") or 10_000)
    n_steps = int(extras.get("n_steps") or 252)
    seed = int(payload.get("seed") or extras.get("seed") or 42)

    try:
        if process == "gbm":
            paths = _gbm_paths(
                S0=float(extras.get("S0") or 100.0),
                mu=float(extras.get("mu") or 0.05),
                sigma=float(extras.get("sigma") or 0.2),
                T=float(extras.get("T") or 1.0),
                n_steps=n_steps,
                n_paths=n_paths,
                seed=seed,
            )
        elif process == "heston":
            paths = _heston_paths(
                S0=float(extras.get("S0") or 100.0),
                v0=float(extras.get("v0") or 0.04),
                kappa=float(extras.get("kappa") or 2.0),
                theta=float(extras.get("theta") or 0.04),
                xi=float(extras.get("xi") or 0.3),
                rho=float(extras.get("rho") or -0.7),
                r=float(extras.get("r") or 0.0),
                T=float(extras.get("T") or 1.0),
                n_steps=n_steps,
                n_paths=n_paths,
                seed=seed,
            )
        elif process == "ou_jump":
            paths = _ou_jump_paths(
                X0=float(extras.get("X0") or 0.0),
                mu=float(extras.get("mu") or 0.0),
                theta_speed=float(extras.get("theta_speed") or 1.0),
                sigma=float(extras.get("sigma") or 0.2),
                jump_intensity=float(extras.get("jump_intensity") or 1.0),
                jump_mean=float(extras.get("jump_mean") or 0.0),
                jump_std=float(extras.get("jump_std") or 0.05),
                T=float(extras.get("T") or 1.0),
                n_steps=n_steps,
                n_paths=n_paths,
                seed=seed,
            )
        elif process == "regime_hmm":
            paths = _regime_hmm_paths(
                S0=float(extras.get("S0") or 100.0),
                mu_high=float(extras.get("mu_high") or 0.10),
                mu_low=float(extras.get("mu_low") or -0.05),
                sigma_high=float(extras.get("sigma_high") or 0.15),
                sigma_low=float(extras.get("sigma_low") or 0.35),
                transition_high_to_low=float(
                    extras.get("transition_high_to_low") or 0.02
                ),
                transition_low_to_high=float(
                    extras.get("transition_low_to_high") or 0.05
                ),
                T=float(extras.get("T") or 1.0),
                n_steps=n_steps,
                n_paths=n_paths,
                seed=seed,
            )
        else:
            return {
                "status": "error",
                "env": "stochastic",
                "error": f"unknown process {process!r}; valid: gbm, heston, ou_jump, regime_hmm",
                "duration_ms": (time.time() - started) * 1000.0,
            }
    except Exception as exc:  # noqa: BLE001
        logger.exception("stochastic simulation failed process=%s", process)
        return {
            "status": "error",
            "env": "stochastic",
            "process": process,
            "error": str(exc),
            "duration_ms": (time.time() - started) * 1000.0,
        }

    finals = paths[:, -1]
    return {
        "status": "done",
        "env": "stochastic",
        "process": process,
        "n_paths": n_paths,
        "summary": {
            "mean_final": float(finals.mean()),
            "std_final": float(finals.std(ddof=1)) if n_paths > 1 else 0.0,
            "p5_final": float(np.quantile(finals, 0.05)),
            "p95_final": float(np.quantile(finals, 0.95)),
            "min_final": float(finals.min()),
            "max_final": float(finals.max()),
        },
        "duration_ms": (time.time() - started) * 1000.0,
    }


__all__ = ["run_stochastic_simulation"]
