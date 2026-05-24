# Weight-centric portfolio pipeline (`f_S -> f_A -> f_T -> f_R`)

> The FinRL-X four-stage protocol that guarantees identical target
> weight semantics across offline backtesting and live broker
> execution.

## Stages

| Stage | Class | Responsibility | Default |
| --- | --- | --- | --- |
| `f_S` (Selector) | [`StockSelector`](../aqp/rl/portfolio/selector.py) | Filter universe by liquidity / vol / momentum | [`StaticUniverseSelector`](../aqp/rl/portfolio/selector.py) |
| `f_A` (Allocator) | [`PortfolioAllocator`](../aqp/rl/portfolio/allocator.py) | Map raw RL action to unconstrained weights | [`IdentityAllocator`](../aqp/rl/portfolio/allocator.py) |
| `f_T` (Timing) | [`TimingAdjuster`](../aqp/rl/portfolio/timing.py) | Scale gross exposure on regime signals | [`ConstantTimingAdjuster`](../aqp/rl/portfolio/timing.py) |
| `f_R` (Risk overlay) | [`RiskOverlay`](../aqp/rl/portfolio/risk_overlay.py) | Truncate weights violating hard constraints | [`StackedRiskOverlay(PositionCap + GrossExposure)`](../aqp/rl/portfolio/risk_overlay.py) |

## Composition

```python
from aqp.rl.portfolio import (
    GrossExposureRiskOverlay,
    IdentityAllocator,
    PositionCapRiskOverlay,
    StackedRiskOverlay,
    StaticUniverseSelector,
    TurbulenceTimingAdjuster,
    WeightCentricPipeline,
)

pipeline = WeightCentricPipeline(
    selector=StaticUniverseSelector(universe=universe),
    allocator=IdentityAllocator(),
    timing=TurbulenceTimingAdjuster(threshold=140.0, cooldown_scale=0.0),
    risk_overlay=StackedRiskOverlay(overlays=[
        PositionCapRiskOverlay(max_position_pct=0.30, mark_truncated=True),
        GrossExposureRiskOverlay(max_gross=1.0),
    ]),
)

state = pipeline.run(
    universe=universe,
    raw_action=action,
    context={"turbulence": 90.0, "prices": prices, "equity": 100_000.0},
)
target_weights = state.weights  # numpy array aligned with state.universe
```

## Determinism contract

Each stage is a **pure function** of its inputs — no hidden global
state, no time-dependent randomness without an explicit seed.
`state.history` records the per-stage weight vector for audit so a
downstream `LedgerWriter` can persist the full
`f_S -> f_A -> f_T -> f_R` trace.

## Truncation propagation

The risk overlay can set `state.context["truncated"]=True` when a
hard constraint is breached (e.g. `mark_truncated=True` on
`PositionCapRiskOverlay`). The
[`RLBacktestEnv`](../aqp/rl/envs/rl_backtest_env.py) lifts this onto
`info["truncated"]` so the
[`StopProperlyWrapper`](../aqp/rl/rewards/stop_properly.py) scales
the step reward by `coef in [0, 1]`.

## Adding a new stage variant

1. Subclass the relevant base
   (`StockSelector` / `PortfolioAllocator` / `TimingAdjuster` /
   `RiskOverlay`).
2. Implement the single transform method
   (`select` / `allocate` / `adjust` / `apply`).
3. Re-export from
   [`aqp/rl/portfolio/__init__.py`](../aqp/rl/portfolio/__init__.py).

## See also

- [aqp_docs/agentic-rl.md](agentic-rl.md) — Overall architecture.
- [Hard rule 38 in AGENTS.md](../AGENTS.md) — Source-of-truth rule.
