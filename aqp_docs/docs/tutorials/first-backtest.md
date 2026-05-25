---
title: 'Your first backtest'
summary: 'Author a momentum strategy, run it through EventDrivenBacktester, inspect the ledger row, render a tearsheet.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 2
runnable: true
---

# Your first backtest

Goal: from blank slate to a backtest with a non-zero Sharpe on
your screen, in under 5 minutes.

## Why

The backtest pipeline is the central artifact of every AQP workflow.
Every strategy gets backtested before paper, every paper run gets
promoted on the back of backtest evidence, and every RL policy gets
evaluated against the same engine. Understanding the backtest
contract is prerequisite to understanding anything else.

## Prerequisites

- The [quickstart](../intro/quickstart.md) completed.
- An open terminal pointing at the repo root.

## Step 1 — author the strategy

Create `configs/strategies/my_first_strategy.yaml`:

```yaml
name: MyFirstMomentum
kind: alpha
class: aqp.strategies.framework.algorithms.MomentumAlpha
module_path: aqp.strategies.framework.algorithms
universe:
  kind: static
  symbols:
    - { ticker: SPY, exchange: ARCA, kind: equity }
    - { ticker: QQQ, exchange: NASDAQ, kind: equity }
    - { ticker: IWM, exchange: ARCA, kind: equity }
kwargs:
  lookback_days: 60
  rebalance_freq: weekly
  top_n: 2
risk:
  max_position_pct: 0.5
  max_drawdown_pct: 0.15
```

The `class` + `module_path` + `kwargs` pattern is Qlib-style and
required for every strategy registry entry. See
[AGENTS rule 8](https://github.com/julianwileymac/agentic_quant_platform/blob/main/AGENTS.md).

## Step 2 — dispatch the backtest

```powershell
docker exec aqp-api python -m aqp.cli.cli backtest \
    --config configs/strategies/my_first_strategy.yaml \
    --start 2024-01-01 \
    --end 2024-06-30 \
    --engine event_driven
```

The CLI returns a `task_id`. Tail its progress:

```powershell
docker exec aqp-api python -c "from aqp.ws.broker import subscribe; \
    [print(m) for m in subscribe('<task_id>')]"
```

You will see progress frames in the canonical
`{task_id, stage, message, timestamp, **extras}` shape.

## Step 3 — inspect the ledger

```powershell
docker exec aqp-postgres psql -U aqp -d aqp -c \
    "SELECT id, strategy_name, sharpe, total_return, max_drawdown
     FROM backtest_runs ORDER BY created_at DESC LIMIT 5;"
```

The most recent row is your run. If `sharpe` is `NULL`, the backtest
failed — see Step 5.

## Step 4 — render a tearsheet

```powershell
curl -X POST http://localhost:8000/analytics/portfolio/tearsheet \
    -H "Content-Type: application/json" \
    -d '{"run_id": "<backtest_run_id_from_step_3>"}'
```

The endpoint returns another `task_id`; the resulting HTML tearsheet
lands at `/analytics/portfolio/<run_id>/tearsheet.html` once Celery
finishes rendering.

Open it in your browser. Or use the operator UI route
[/analytics/portfolio/:runId](http://localhost:3001/analytics/portfolio).

## Step 5 — handle expected failures

**`InsufficientDataError`** — Alpha Vantage has not seeded the
universe yet. Run the ingest:

```powershell
docker exec aqp-api python -m scripts.ingest_yfinance \
    --symbols SPY,QQQ,IWM --start 2023-01-01 --end 2024-12-31
```

**`StrategyRegistryMissError`** — the YAML's `class` field
references a class that is not decorated with `@register`. Open
[aqp/strategies/framework/algorithms.py](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/strategies/framework/algorithms.py)
and confirm `MomentumAlpha` is there. If you renamed the class,
update the YAML.

**`IcebergNamespaceError`** — your local Iceberg catalog has not
been migrated. Run `make iceberg-bootstrap` and retry.

## Verify

- [ ] `backtest_runs` row visible with non-NULL `sharpe`.
- [ ] Tearsheet HTML renders.
- [ ] Strategy YAML committed under `configs/strategies/`.

## What next

- [Concept: backtest engines](../concepts/strategy/backtest-engines.md) —
  what `event_driven` vs `vbtpro` vs `hft` actually does.
- [Recipe: run a backtest from YAML](../how-to/recipes/run-a-backtest-from-yaml.md) —
  the same thing, but as a how-to for repeated dispatch.
- [Tutorial: first bot](./first-bot.md) — wrap this strategy in a
  reusable bot spec.
