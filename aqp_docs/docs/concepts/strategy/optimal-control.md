---
title: 'Optimal-control / HJB math layer'
summary: 'The optimal-control package — [aqp/optimal_control/](../aqp/optimal_control/) — hosts the JAX-compiled implementations of two canonical Hamilton-Jacobi-Bellman problems:'
owner: strategy-team
last_reviewed: 2026-05-25
audience: both
---

# Optimal-control / HJB math layer

> **Audience:** quants extending AQP with optimal-execution or
> market-making models, plus AI agents that need to reason about
> the closed-form solvers.

The optimal-control package — [aqp/optimal_control/](../aqp/optimal_control/) — hosts
the JAX-compiled implementations of two canonical Hamilton-Jacobi-Bellman
problems:

- **Avellaneda-Stoikov 2008** market making —
  [aqp/optimal_control/avellaneda_stoikov.py](../aqp/optimal_control/avellaneda_stoikov.py).
- **Cartea-Jaimungal-Penalva 2015** inventory-penalised optimal liquidation —
  [aqp/optimal_control/cartea_jaimungal.py](../aqp/optimal_control/cartea_jaimungal.py).

The convenience layer [aqp/optimal_control/hjb_solver.py](../aqp/optimal_control/hjb_solver.py)
exposes ``solve_avst`` / ``solve_cj`` / ``value_function_to_arrow`` so the
analysis-flow runner can dispatch them uniformly and persist the
results to ``aqp_gold_analysis_optimal_control`` per AGENTS rule 21.

## Where to invoke

Three call sites cover almost every use case.

### 1. Direct Python API

```python
from aqp.optimal_control import compute_optimal_quotes, solve_avst

# Single-point AvSt quotes — pure JIT-compiled JAX path.
res = compute_optimal_quotes(
    mid_price=100.0,
    inventory=10.0,
    gamma=0.1,
    sigma=0.02,
    k=1.5,
    T_minus_t=1.0,
)
print(res.bid, res.ask, res.half_spread)

# Inventory grid via vmap.
out = solve_avst(
    mid_price=100.0,
    inventory_grid=[-50, -25, 0, 25, 50],
    gamma=0.1, sigma=0.02, k=1.5, T_minus_t=1.0,
)
```

### 2. Analysis flows (preferred — gives you UI form + Iceberg persistence)

```python
from aqp.analysis import run_flow

result = run_flow(
    "optimal_control.avellaneda_stoikov_quotes",
    None,
    {
        "mid_price": 100.0,
        "inventory_min": -50.0,
        "inventory_max": 50.0,
        "inventory_step": 5.0,
        "gamma": 0.1, "sigma": 0.01, "k": 1.5, "T_minus_t": 1.0,
    },
)
```

The flow is a thin facade over ``solve_avst`` and writes its rows to
the gold-tier ``aqp_gold_analysis_optimal_control.<table>`` namespace
when invoked through ``AnalysisRuntime``.

### 3. Agent-callable DataMCPTool

```python
# inside an AgentSpec body the tool surfaces as ``data.optimal_control.solve_hjb``
result = ctx.tools["data.optimal_control.solve_hjb"].invoke(
    ctx=mcp_ctx, model="avst", mid_price=100.0, inventory=10.0,
    gamma=0.1, sigma=0.01, k=1.5, T_minus_t=1.0,
)
```

The tool is registered in
[aqp/data/mcp/tools/optimal_control.py](../aqp/data/mcp/tools/optimal_control.py)
and complies with AGENTS rule 22 — agents never read Iceberg / Postgres
directly.

## Avellaneda-Stoikov (single-asset)

Reservation price plus optimal half-spread:

```
r(s, q, t) = s − q · γ · σ² · (T − t)
δ        = ½ · γ · σ² · (T − t) + (1/γ) · ln(1 + γ/k)
bid       = r − δ
ask       = r + δ
```

The JAX kernel ``_avst_kernel`` is JIT-compiled with ``@jax.jit`` and
takes only Python floats / arrays — no I/O, no globals, no Python
control flow keyed on values. ``vmap`` lets us evaluate the kernel
across an inventory grid in one compiled call.

The closed-form GLFT 2013 variant (
``glft_closed_form``) is what
[aqp.strategies.hft.alphas.GLFTMM](../aqp/strategies/hft/alphas.py)
calls on every event. Its ``2/γ · ln(1 + γ/k)`` term differs from the
finite-horizon AvSt ``1/γ · ln(...)`` by a factor of two — that's the
long-horizon limit.

## Cartea-Jaimungal-Penalva (inventory-penalised liquidation)

Linear-quadratic ansatz ``H(t, q, S) = q·S + h₂(t)·q² + h₁(t)·q + h₀(t)``
reduces the HJB to a system of three coupled ODEs:

```
dh₂/dt = −φ − h₂² / κ
dh₁/dt = −h₁ · h₂ / κ
dh₀/dt = −h₁² / (4 · κ)
```

Solved backwards from the terminal conditions ``h₂(T) = −α`` and
``h₁(T) = h₀(T) = 0`` via fixed-step RK4. The optimal feedback
trading rate is

```
ν*(t, q) = − (h₂(t) · q + ½ · h₁(t)) / κ
```

When ``φ > 0`` the agent sells (or buys) faster than TWAP near the
terminal because ``h₂`` decreases; when ``φ = 0`` the rate collapses to
zero (no urgency).

## Pairing with reinforcement learning

The closed forms are reference benchmarks. To learn a richer policy
for non-Gaussian dynamics, drive an RL agent through:

- [aqp.rl.envs.MarketMakingEnv](../aqp/rl/envs/market_making_env.py) —
  PPO/SAC over AvSt knobs.
- [aqp.rl.envs.OptimalExecutionEnv](../aqp/rl/envs/optimal_execution_env.py) —
  Cartea-Jaimungal block liquidation.

Sample experiment YAMLs ship under [configs/rl/](../configs/rl/)
(``avellaneda_stoikov_mm.yaml``, ``cartea_jaimungal_execution.yaml``).

## See also

- [aqp_docs/portfolio-options-mm.md](../../concepts/strategy/portfolio-options-mm.md) — Lucic-Tse
  multi-strike extension.
- [aqp_docs/microstructure-toxicity.md](../../concepts/strategy/microstructure-toxicity.md) —
  toxicity regime detection + agent adapter loop.
- [aqp_docs/installation.md](../../intro/installation.md) — how to install the
  ``[optimal-control]`` extra (JAX, finhjb, fast-vollib, mbt_gym).
