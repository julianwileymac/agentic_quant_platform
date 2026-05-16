# Experiments + Tests umbrella (Phase 1 of the multi-tenant rollout)

The umbrella sits **above** every existing typed run table so the
"what was the user trying?" question gets one consistent answer
regardless of which downstream engine produced the artefact.

## Tables

| Table | Purpose | Key columns |
| ----- | ------- | ----------- |
| `experiments` | User-driven container; one row per hypothesis / sweep / iteration | `id`, `slug`, `name`, `kind` (`ml`/`rl`/`analysis`/`backtest`/`paper`/`bot`/`agent`/`research`/`hypothesis`/`optimization`/`ablation`/`sweep`), `status`, `parent_experiment_id`, `lab_id`, `metrics jsonb` |
| `tests` | Pass/fail-style assertions attached to an experiment | `id`, `experiment_id`, `slug`, `name`, `assertion_kind`, `passed`, `details jsonb`, `run_ref_table`, `run_ref_id` |

Both inherit `ProjectScopedMixin` (`owner_user_id` / `workspace_id` /
`project_id`).

## Linkage to typed runs

Migration 0037 added nullable `experiment_id` (and `test_id` where it
applies) columns to:

- `backtest_runs`
- `ml_experiment_runs`
- `rl_runs`
- `analysis_runs`
- `bot_deployments`
- `strategy_tests` (also gets `test_id`)
- `paper_trading_runs`
- `agent_runs_v2`
- `agent_runs`

Existing rows stay at `NULL`; only new flows opt in. The
[`LedgerWriter`](../aqp/persistence/ledger.py) `_stamp` chain copies
`RequestContext.experiment_id` / `.test_id` onto every row that
has the matching attribute, so most flows just need a populated
`RequestContext` to flow through.

## Hard rule

Hard rule 34 in [`AGENTS.md`](../AGENTS.md): "Every new
run-producing flow MUST populate `experiment_id` (and `test_id`
where applicable) on its run row. Don't add a new `*_runs` table
without an `experiment_id` FK."

## REST surface

| Method + path                              | Purpose |
| ------------------------------------------ | ------- |
| `GET /experiments`                         | List (filter by `project_id`, `kind`, `status`, `parent_experiment_id`) |
| `POST /experiments`                        | Create (slug auto-derived from name) |
| `GET /experiments/{id}`                    | Describe |
| `PATCH /experiments/{id}`                  | Update (status/metrics/parent) |
| `DELETE /experiments/{id}`                 | Cascade-deletes tests |
| `GET /experiments/{id}/runs`               | Stitched view of every typed run row pointing here |
| `GET /tests`                               | List (filter by `experiment_id`, `passed`, `assertion_kind`) |
| `POST /tests`                              | Create attached to an experiment |
| `GET /tests/{id}`                          | Describe |
| `POST /tests/{id}/evaluate`                | Set the pass/fail verdict + ref into a typed run row |

## MCP surface

- `data.experiments.list` — list / filter.
- `data.experiments.tree` — nested view (`PARENT_OF` chain).
- `data.experiments.describe` — full row + counts of linked runs.
- `data.tests.list` — list / filter.
- `data.tests.describe` — full row.

## Cross-reference

- The Phase 2 ownership graph projects every experiment +
  test + linked run into Neo4j. See
  [`docs/ownership-graph.md`](ownership-graph.md).
- The Phase 6 frontend ContextBar lets the user pin a specific
  experiment (when the route declares one). See the route handlers
  for which surfaces opt in.
- The Phase 7 LEAN clone-to-workspace flow optionally creates an
  experiment when the user provides a name. See
  [`docs/strategy-templates.md`](strategy-templates.md).
