---
title: 'Quickstart'
summary: 'Stand up an AQP dev stack and run your first backtest in under 30 seconds of typing.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 2
---

# Quickstart

Target: a fresh checkout of `agentic_quant_platform` to a green backtest
result in under 30 seconds of typing (plus first-time Docker image
pull, which is unavoidable).

## Prerequisites

- Docker Desktop or compatible engine running locally.
- Python 3.11 and `make` on your PATH.
- The repo cloned to disk.

## One-paste quickstart

```powershell
# 1. Pull the canonical compose stack.
make dev

# 2. Wait for /readyz to return 200.
curl http://localhost:8000/readyz

# 3. Run the bundled example backtest.
docker exec aqp-api python -m aqp.cli.cli backtest \
    --config configs/strategies/momentum_demo.yaml \
    --start 2024-01-01 --end 2024-06-30
```

If the third command returns a JSON summary with non-zero `sharpe` and
`total_return`, your dev stack is healthy.

## What just happened

- `make dev` boots the canonical compose profile defined in
  [aqp_platform/deployments/compose/docker-compose.dev.yml](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_platform/deployments/compose/docker-compose.dev.yml).
  This brings up Postgres + Redis + the Iceberg REST catalog +
  `aqp-core` (FastAPI) + `aqp-worker` (Celery) + `aqp-beat`.
- `curl http://localhost:8000/readyz` confirms the FastAPI gateway is
  serving requests against a migrated Postgres schema. Migrations run
  automatically on first boot via the `aqp-api` container's
  `entrypoint.sh`.
- The backtest command dispatches a Celery task that pulls the
  example momentum strategy, runs it against the seeded data, and
  writes a `backtest_runs` ledger row.

## Next steps

1. Want to see the run in the UI? Open
   [http://localhost:3001](http://localhost:3001) — that is the
   Vite operator UI ([aqp_client](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp_client)).
2. Want to add your own strategy? Read
   [Recipe: Add a strategy](../how-to/recipes/add-a-strategy.md).
3. Want to set up paper trading? Read
   [Concept: paper trading](../concepts/trading/paper-trading.md)
   followed by
   [Tutorial: first paper trading session](../tutorials/first-paper-trading-session.md).
4. Want to deploy this to Kubernetes? Read
   [How-to: Kubernetes deploy](../how-to/operations/kubernetes-deploy.md).

## If it does not work

The `/readyz` probe is the single canonical health check. If it returns
non-200 within 60 seconds:

- Check `docker compose logs aqp-api` for migration errors.
- Confirm Postgres is reachable: `docker exec aqp-postgres pg_isready`.
- Confirm Redis is reachable: `docker exec aqp-redis redis-cli ping`.
- Verify the Iceberg REST catalog is up:
  `curl http://localhost:8181/v1/config`.

If the backtest command itself errors out, the most common cause is a
stale Iceberg manifest from a prior dev cycle. Tear down with
`make down && docker volume prune -f` and re-run.

For deeper debugging, see [How-to: incident response](../how-to/operations/incident-response.md).
