---
title: 'Portfolio options market making — Lucic-Tse 2024-2026'
summary: 'The single-asset Avellaneda-Stoikov framework breaks down for options portfolios. An options book carries simultaneous Δ / Γ / ν / ρ exposures across hundreds of strikes; the spread the dealer should ...'
owner: strategy-team
last_reviewed: 2026-05-25
audience: both
---

# Portfolio options market making — Lucic-Tse 2024-2026

> **Audience:** options market-makers, quant developers writing
> spread-prediction models, and agents that need to reason about
> portfolio-level risk skew.

The single-asset Avellaneda-Stoikov framework breaks down for options
portfolios. An options book carries simultaneous Δ / Γ / ν / ρ
exposures across hundreds of strikes; the spread the dealer should
quote at strike ``K`` is no longer independent of the inventory at
strike ``K′``.

The breakthrough closed-form solution for portfolio-level options MM
landed in 2024-2026: V. Lucic and A. Tse, *"Optimal option market
making and volatility arbitrage"*. AQP implements that framework in
[aqp/options/portfolio_mm.py](../aqp/options/portfolio_mm.py).

## Two equations

**1. Per-strike vol-arb alpha.**

```
α(K, T) = ½ · S² · Γ(K, T) · (σ_real² − σ_imp²)
```

This is the option-equivalent of the spot vol-arb edge: when realised
volatility exceeds implied volatility, the dealer collects vega
exposure at a positive expected value.

**2. Inventory-skewed bid/ask quote.**

```
bid(K, T)  = mid(K, T) − δ(K, T) − skew(K, T)
ask(K, T)  = mid(K, T) + δ(K, T) − skew(K, T)
δ(K, T)    = base_spread + ½ · hedge_cost · |Γ(K, T)|
skew(K, T) = γ_inv · ν(K, T) · (Σ_vol · q_per_expiry)
```

where ``Σ_vol`` is the (rank-reducible) covariance of the implied-vol
factors across maturities and ``q`` is the inventory matrix.

The Riccati system the linear-quadratic ansatz produces is closed-form
in steady state — no PDE solver required. AQP implements that closed
form in pure JAX with ``jnp.einsum`` for the matrix contractions.

## Calling the solver

```python
import numpy as np
from aqp.analysis.pricing import greeks_grid
from aqp.options.portfolio_mm import LucicTseParams, compute_lucic_tse_quotes

strikes = np.array([95., 100., 105.])
expiries = np.array([0.05, 0.1, 0.25])

grid = greeks_grid(spot=100., strikes=strikes, expiries=expiries, vol=0.2)
quotes = compute_lucic_tse_quotes(
    spot=100.0,
    mid_quotes=grid["price"],
    gamma_surface=grid["gamma"],
    vega_surface=grid["vega"],
    realized_vol=0.22,            # the dealer's view
    implied_vol=np.full_like(grid["price"], 0.20),  # market quote
    inventory=np.zeros_like(grid["price"]),
    params=LucicTseParams(gamma_inv=0.05, base_spread=0.05, hedge_cost=0.001),
)
print(quotes.bid)         # (n_expiries, n_strikes)
print(quotes.ask)
print(quotes.expected_pnl)
```

JAX optionality: when the ``[optimal-control]`` extra is missing, the
module degrades to NumPy. Numerical results are identical, just slower.

## Analysis-flow surface

For UI / agent flows, use ``optimal_control.lucic_tse_portfolio_quotes``
or the namespace alias ``derivatives.lucic_tse_quotes``. Both wrap
``compute_lucic_tse_quotes`` and persist a row-per-cell table to
``aqp_gold_analysis_optimal_control.lucic_tse_portfolio_quotes``.

```python
from aqp.analysis import run_flow

out = run_flow(
    "optimal_control.lucic_tse_portfolio_quotes",
    None,
    {
        "spot": 100.0,
        "strikes": [90, 95, 100, 105, 110],
        "expiries": [0.05, 0.1, 0.25, 0.5],
        "realized_vol": 0.22,
        "implied_vol": 0.20,
        "gamma_inv": 0.05,
        "base_spread": 0.05,
        "hedge_cost": 0.001,
    },
)
```

## Pairing with the JAX/fast-vollib Greek path

Building the Greek surface dominates the per-step cost. AQP ships a
JAX/vmap drop-in path in
[aqp/options/greeks_jax.py](../aqp/options/greeks_jax.py) that
auto-detects ``fast_vollib`` (Triton-fused on H100) when the extra is
installed, otherwise JIT-compiles a hand-rolled BSM kernel. The legacy
``aqp.analysis.pricing.greeks_grid`` routes through this fast path
automatically.

## RL pairing

[aqp.rl.envs.LucicTsePortfolioEnv](../aqp/rl/envs/lucic_tse_options_env.py)
exposes the framework as a Gym environment so PPO/SAC can learn to
adapt ``γ_inv`` / ``base_spread`` as a function of the realised vs
implied gap. Sample config: [configs/rl/lucic_tse_options.yaml](../configs/rl/lucic_tse_options.yaml).

## See also

- [aqp_docs/optimal-control.md](../../concepts/strategy/optimal-control.md) — single-asset HJB.
- [aqp_docs/microstructure-toxicity.md](../../concepts/strategy/microstructure-toxicity.md) — the
  toxicity-aware regime adapter that scales ``γ_inv`` automatically
  during toxic flow.
