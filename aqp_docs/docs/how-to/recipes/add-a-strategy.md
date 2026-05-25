---
title: 'Recipe: add a strategy'
summary: 'The minimum-viable steps to register a new strategy class against the AQP registry.'
owner: strategy-team
last_reviewed: 2026-05-25
audience: both
---

# Recipe: add a strategy

The 5-minute happy path:

1. Subclass `IStrategy` (or `FrameworkAlgorithm`) under
   [aqp/strategies/](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp/strategies).
2. Decorate with `@register("MyName", kind="alpha")` from
   [aqp/core/registry.py](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/core/registry.py).
3. Ship a YAML at `configs/strategies/<my-name>.yaml` using the
   `class` / `module_path` / `kwargs` factory pattern.
4. Smoke-test:

```powershell
docker exec aqp-api python -m aqp.cli.cli backtest \
    --config configs/strategies/<my-name>.yaml \
    --start 2024-01-01 --end 2024-06-30
```

If the smoke run lands a `backtest_runs` row with a non-NULL
`sharpe`, you are done.

## Pitfalls

- **Forgetting `@register`.** YAML loaders fail silently; the run
  errors out as `StrategyRegistryMissError`.
- **Putting strategy logic in a route or task.** Don't. Routes thin
  wrap Celery tasks; Celery tasks thin wrap pure functions under
  `aqp/strategies/`. See [AGENTS Don'ts](https://github.com/julianwileymac/agentic_quant_platform/blob/main/AGENTS.md).
- **Skipping risk overlays.** Every strategy ships with a `risk:`
  block in YAML. Without it, the paper-metadata gate refuses to
  promote the strategy.

## Deeper reads

- [Concept: factor research](../../concepts/strategy/factor-research.md)
- [Concept: backtest engines](../../concepts/strategy/backtest-engines.md)
- [Tutorial: first backtest](../../tutorials/first-backtest.md)
