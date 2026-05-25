---
title: 'Recipe: run a backtest from YAML'
summary: 'Dispatch a backtest task from a YAML strategy config and tail the Celery progress.'
owner: strategy-team
last_reviewed: 2026-05-25
audience: both
---

# Recipe: run a backtest from YAML

```powershell
$resp = curl -X POST http://localhost:8000/backtest `
    -H "Content-Type: application/json" `
    -d (Get-Content configs/strategies/my-strategy.yaml -Raw)

# Tail progress (canonical {task_id, stage, message, timestamp} frames).
docker exec aqp-api python -c "from aqp.ws.broker import subscribe; \
    [print(m) for m in subscribe('<task_id>')]"
```

## Choose your engine

The default engine is `vbtpro` (vectorbt-pro primary). Override
with `--engine event_driven` / `hft` / `vectorbt` / `backtesting_py`
/ `zvt` / `aat`. See [backtest engines](../../concepts/strategy/backtest-engines.md)
for the capability matrix and fallback cascade.

## Walk-forward + WFO

```powershell
curl -X POST http://localhost:8000/backtest/wfo `
    -d '{"strategy_config":"configs/strategies/my-strategy.yaml","windows":12,"step":"1mo"}'
```

The endpoint dispatches one task per window; each writes its own
`backtest_runs` row and the parent emits a `wfo.complete` frame
when every window is in.

## Look at results

- `backtest_runs` row in Postgres for the headline metrics.
- `aqp_gold_backtest_<run_id>` Iceberg namespace for trade-level
  detail.
- The QuantStats tearsheet endpoint at
  `POST /analytics/portfolio/tearsheet` for an HTML report.

## Deeper reads

- [Tutorial: first backtest](../../tutorials/first-backtest.md) —
  end-to-end walkthrough.
- [Concept: backtest engines](../../concepts/strategy/backtest-engines.md)
- [Concept: analytics frontend](../../concepts/data/analytics-frontend.md)
