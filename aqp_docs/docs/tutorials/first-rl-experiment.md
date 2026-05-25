---
title: 'Your first RL experiment'
summary: 'Author an RLExperimentSpec, train via SB3 PPO, replay from the Iceberg trajectory store.'
owner: rl-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 4
---

# Your first RL experiment

Goal: from blank `RLExperimentSpec` to a trained PPO agent with
trajectories persisted to Iceberg, in under 10 minutes on CPU.

## Why

The RL stack is AQP's most opinionated subsystem: hash-locked
`RLExperimentSpec`, metaclass-registered components, deterministic
Iceberg trajectory persistence, and a single sanctioned executor
([`RLRuntime`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_rl/src/aqp_rl/runtime.py)).
Every RL run produces an immutable `rl_runs` ledger row and a
replayable trajectory.

See [Concept: RL framework](../concepts/rl/rl-framework.md).

## Prerequisites

- Quickstart completed.
- A small dev dataset under your local Iceberg catalog. The bundled
  `aqp_bronze_yfinance_daily` namespace works.

## Step 1 — author the spec

Create `aqp_rl/configs/experiments/my_first_rl.yaml`:

```yaml
name: MyFirstRLExperiment
description: First-RL tutorial — PPO on a static universe
environment:
  rl_alias: SingleAssetTradingEnv
  symbol: { ticker: SPY, exchange: ARCA, kind: equity }
  lookback_bars: 60
  initial_cash: 100000
data_pipeline:
  rl_alias: IcebergDataPipeline
  namespace: aqp_bronze_yfinance_daily
  start: 2022-01-01
  end: 2023-12-31
agent:
  rl_alias: SB3Adapter
  algorithm: PPO
  policy: MlpPolicy
  total_timesteps: 50000
rewards:
  - { rl_alias: PnLReward, weight: 1.0 }
  - { rl_alias: TurnoverPenalty, weight: 0.1 }
  - { rl_alias: VolatilityPenalty, weight: 0.05 }
observations:
  - { rl_alias: StockstatsObservation }
  - { rl_alias: LookbackObservation, length: 20 }
training:
  advantage: { rl_alias: GAEAdvantage, lambda: 0.95, gamma: 0.99 }
  backbone: { rl_alias: TransformerBackbone, d_model: 64, n_heads: 4 }
```

## Step 2 — snapshot + train

```powershell
curl -X POST http://localhost:8000/rl/runs \
    -H "Content-Type: application/json" \
    -d '{"spec_path":"aqp_rl/configs/experiments/my_first_rl.yaml","mode":"train"}'
```

The response includes the `rl_run_id`. Tail the progress:

```powershell
docker exec aqp-api python -c "from aqp.ws.broker import subscribe; \
    [print(m) for m in subscribe('<task_id>')]"
```

50k timesteps on a CPU finishes in 5-8 minutes.

## Step 3 — inspect the ledger + trajectory store

```sql
-- rl_runs ledger
SELECT id, experiment_name, status, total_timesteps, mean_reward
FROM rl_runs ORDER BY created_at DESC LIMIT 5;
```

The trajectory data lives in Iceberg under
`aqp_silver_rl_trajectories.<experiment_hash>`:

```python
from pyiceberg.catalog import load_catalog
cat = load_catalog("aqp")
tbl = cat.load_table("aqp_silver_rl_trajectories.<hash>")
df = tbl.scan().to_pandas()
print(df[["episode", "step", "reward", "action"]].head(20))
```

## Step 4 — replay

```powershell
curl -X POST http://localhost:8000/rl/runs/<rl_run_id>/replay \
    -d '{"start":"2024-01-01","end":"2024-03-31"}'
```

Same hash-locked spec, new data window, separate `rl_runs` row.

## Step 5 — halt

```powershell
curl -X POST http://localhost:8000/rl/halt-all
```

## Verify

- [ ] `rl_experiment_versions` row with a `spec_hash`.
- [ ] `rl_runs` row with non-NULL `mean_reward`.
- [ ] Iceberg trajectory table populated.
- [ ] Replay produces a different `rl_runs` row but reuses the
  same `rl_experiment_versions` row (hash-locked!).

## What next

- [Concept: RL components](../concepts/rl/rl-components.md) — add
  your own reward term, observation builder, or policy backbone.
- [Concept: RL Iceberg trajectories](../concepts/rl/rl-iceberg.md) —
  the persistence contract.
- [Tutorial: first agent workflow](./first-agent-workflow.md) —
  hand off RL outputs to an autonomous agent loop.
