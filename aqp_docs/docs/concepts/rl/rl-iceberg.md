---
title: 'RL Iceberg data plane'
summary: '| Table | Columns | Written when | | --- | --- | --- | | `rl.trajectories` | `run_id`, `episode`, `step`, `ts`, `reward`, `info` (JSON) | Every env step | | `rl.equity_curves` | `run_id`, `episode`, `...'
owner: rl-team
last_reviewed: 2026-05-25
audience: both
---

# RL Iceberg data plane

Per-step RL records persist to four Iceberg tables in the namespace
controlled by `AQP_RL_TRAJECTORY_NAMESPACE` (default `rl`). Writes flow
through
[`aqp/rl/trajectories/iceberg_writer.py::IcebergTrajectoryStore`](../aqp/rl/trajectories/iceberg_writer.py)
→ [`iceberg_catalog.append_arrow`](../aqp/data/iceberg_catalog.py).

## Tables

| Table | Columns | Written when |
| --- | --- | --- |
| `rl.trajectories` | `run_id`, `episode`, `step`, `ts`, `reward`, `info` (JSON) | Every env step |
| `rl.equity_curves` | `run_id`, `episode`, `step`, `ts`, `portfolio_value`, `drawdown`, `cash` | Every env step that exposes `info["portfolio_value"]` |
| `rl.action_logs` | `run_id`, `episode`, `step`, `ts`, `asset_idx`, `action_value` | Every env step (one row per action component) |
| `rl.reward_decomposition` | `run_id`, `episode`, `step`, `ts`, `term_name`, `contribution` | When the reward model exposes `info["reward_terms"]` (any `CompositeReward`) |

## Settings

| Variable | Default | Purpose |
| --- | --- | --- |
| `AQP_RL_TRAJECTORY_NAMESPACE` | `rl` | Iceberg namespace |
| `AQP_RL_TRAJECTORY_TABLE` | `trajectories` | Per-step trajectory table name |
| `AQP_RL_EQUITY_TABLE` | `equity_curves` | Equity-curve table name |
| `AQP_RL_ACTION_LOG_TABLE` | `action_logs` | Action-log table name |
| `AQP_RL_REWARD_DECOMP_TABLE` | `reward_decomposition` | Reward-decomposition table name |
| `AQP_RL_PERSIST_TRAJECTORIES` | `true` | When `false`, the runtime uses an in-memory store (CI / local). |
| `AQP_RL_TRAJECTORY_FLUSH_ROWS` | `1000` | Rows per buffer before partial flush. |
| `AQP_RL_REQUIRE_ICEBERG` | `false` | Make Iceberg write failures hard-fail. |

## DuckDB views

[`aqp/rl/trajectories/duckdb_views.py`](../aqp/rl/trajectories/duckdb_views.py)
exposes two helpers:

- `ensure_duckdb_views(connection)` — registers
  `rl_trajectories` / `rl_equity_curves` / `rl_action_logs` /
  `rl_reward_decomposition` Arrow-backed views.
- `register_run_views(run_id, connection)` — adds run-filtered views
  named `rl_<kind>_run_<short_id>`.

The API uses these views to serve the
`/rl/runs/{id}/equity` / `/trajectories` / `/reward-decomposition` /
`/actions` endpoints without touching PyIceberg directly.

## Postgres ledger

The Postgres tables in
[`aqp/persistence/models_rl.py`](../aqp/persistence/models_rl.py)
hold the metadata layer that points at these Iceberg row ranges:

- `rl_experiment_specs` / `rl_experiment_versions` — hash-locked spec
  snapshots.
- `rl_runs` — one row per `RLRuntime` invocation.
- `rl_evaluations` — rollout summary.
- `rl_trajectory_refs` / `rl_equity_curve_refs` — pointers to the
  Iceberg row ranges per episode.
- `rl_component_registrations` — DB mirror of the in-memory RL
  component registry (so `/rl/components` is fast).
