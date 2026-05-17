# Orchestration control plane refactor — rollout runbook

This is the operator-facing rollback / rollout guide for the additive
``WorkflowRuntime`` + ``OrchestrationAdapter`` stack landed by the
seven phases described in
[AQP_REFACTOR_MASTER_PROMPT.md](../AQP_REFACTOR_MASTER_PROMPT.md) and
the matching cursor plan. Every change in the refactor is gated by
one of the ``AQP_ORCHESTRATION_*`` flags defined on
[aqp/config/settings.py](../aqp/config/settings.py); **with every
flag at its default ``False`` the platform behaves identically to the
pre-refactor build**. The Phase 0 regression test
[tests/agents/test_orchestration_flags.py](../tests/agents/test_orchestration_flags.py)
enforces this — run it before flipping anything.

## Flag inventory

| Flag (env var prefix `AQP_`) | Default | Activates | First needed in |
| --- | --- | --- | --- |
| `ORCHESTRATION_STUDIO_ENABLED` | `false` | `/workflows/*` API surface, Vite studio routes, `WorkflowSpec` registry persistence | Phase 5 |
| `ORCHESTRATION_CREW_ADAPTER_ENABLED` | `false` | `CrewProcessAdapter` registration (`crewai` stays an optional import) | Phase 2 |
| `ORCHESTRATION_FUSION_ENABLED` | `false` | `SignalFusionAdapter` + `WeightCentricExecutionAdapter` + `build_dialectical_with_fusion_graph` | Phase 4 |
| `ORCHESTRATION_SCHEDULE_ENABLED` | `false` | `AutomationScheduleAdapter` Celery beat entry | Phase 3 |
| `ORCHESTRATION_WORKFLOW_VERSIONING_ENABLED` | `false` | Snapshots `WorkflowSpec` into `workflow_spec_versions` on first run | Phase 5 |
| `ORCHESTRATION_KILL_PROPAGATION_ENABLED` | `false` | Watchdog + KillSwitch UI fan halts into `WorkflowRun` rows | Phase 6 |
| `ORCHESTRATION_MAX_DEBATE_ROUNDS` (int) | `2` | Hard cap enforced by `DialecticalDebateAdapter` and the graph builder | Phase 2 |
| `ORCHESTRATION_HALT_CHECK_TIMEOUT_SECONDS` (float) | `1.0` | Per-transition halt-check budget in `WorkflowRuntime` | Phase 2 |

The two numeric knobs are read every transition, so changing them
takes effect on the next workflow step without a restart.

## Recommended rollout order

1. **Phase 0 → Phase 1**: deploy with every flag at default. Run the
   full pytest suite plus
   [tests/agents/test_orchestration_flags.py](../tests/agents/test_orchestration_flags.py)
   to confirm zero behavioural drift.
2. **Phase 2 (debate)**: flip `ORCHESTRATION_CREW_ADAPTER_ENABLED` if
   you want CrewAI-backed crew adapters to register; otherwise leave
   off. The bounded-debate cap is always honoured by the new graph
   builder kwarg regardless of this flag.
3. **Phase 3 (scheduler)**: flip `ORCHESTRATION_SCHEDULE_ENABLED` AFTER
   restarting Celery workers + beat. The flag controls whether
   `aqp.tasks.celery_app` registers the beat schedule entry.
4. **Phase 4 (fusion)**: flip `ORCHESTRATION_FUSION_ENABLED` only after
   confirming the existing `risk_simulator_approves` predicate still
   routes correctly on a staging dataset — fusion adds a sibling
   pathway, the existing risk gate stays authoritative.
5. **Phase 5 (studio)**: flip `ORCHESTRATION_STUDIO_ENABLED` and
   `ORCHESTRATION_WORKFLOW_VERSIONING_ENABLED` together. Apply the
   alembic migration `0046_workflow_versioning.py` BEFORE the flag is
   flipped on the API process.
6. **Phase 6 (halt fan-out)**: flip
   `ORCHESTRATION_KILL_PROPAGATION_ENABLED` last. The KillSwitch UI
   keeps its existing behaviour with this flag off; turning it on
   adds workflow-run fan-out to the existing `/agents/halt`,
   `/paper/stop-all`, `/bots/halt-all`, `/rl/halt-all`, and
   `/quant-agents/halt` fan-out.

## Rollback recipes

All rollbacks are flag-flips (no migrations, no data loss):

- **Disable studio + API**: set `AQP_ORCHESTRATION_STUDIO_ENABLED=false`
  and reload the API. The `/workflows/*` routes refuse new requests
  with `503 Service Unavailable` while the rest of the API keeps
  serving.
- **Disable scheduler**: set `AQP_ORCHESTRATION_SCHEDULE_ENABLED=false`
  and restart Celery beat. Already-running scheduled runs finish
  normally; no new ones are enqueued.
- **Disable fusion**: set `AQP_ORCHESTRATION_FUSION_ENABLED=false` and
  reload. The optional
  `build_dialectical_with_fusion_graph` builder refuses to compile;
  existing builders are unaffected.
- **Disable kill fan-out**: set
  `AQP_ORCHESTRATION_KILL_PROPAGATION_ENABLED=false`. The KillSwitch
  UI keeps its existing five halt buttons (agents / paper / bots /
  rl / quant-agents); the new "Halt workflows" button no-ops.
- **Disable workflow versioning**: set
  `AQP_ORCHESTRATION_WORKFLOW_VERSIONING_ENABLED=false`. New runs
  refuse to snapshot a spec hash; existing `workflow_spec_versions`
  rows stay readable.
- **Full revert**: set every `AQP_ORCHESTRATION_*` flag to `false`,
  redeploy. The platform behaves exactly like the pre-refactor build.
  The new tables (`workflow_specs`, `workflow_spec_versions`,
  `workflow_runs`) stay empty and add no read overhead to other
  routes.

## Migration safety

- The single new migration `0046_workflow_versioning.py` is additive:
  it creates three new tables and adds no columns to existing
  tables. Downgrade returns the database to the
  `0045_pgvector_foundation` head.
- The new `aqp.tasks.orchestration_tasks` module appends to the
  Celery `include` list; cold installs without the module fail
  loudly at worker boot rather than silently dropping tasks.
- The Vite studio bundle is code-split: routes under
  `frontend/src/routes/workflows/*` lazy-load only when the user
  navigates there, so disabling the flag also disables the
  bundle download path.

## Pre-flip checklist

Run before flipping any flag in production:

1. `docker exec aqp-api python -m pytest tests/agents/test_orchestration_flags.py -v`
2. `docker exec aqp-api python -m pytest tests/agents/test_watchdog.py -v`
3. `docker exec aqp-api alembic current` — confirm head is at least
   `0045_pgvector_foundation`; for Phase 5+ confirm `0046_workflow_versioning`.
4. Snapshot the Redis kill-switch key
   (`redis-cli get $AQP_RISK_KILL_SWITCH_KEY`) — the watchdog uses
   the same key so the new gate stays consistent.

## Where each layer lives

- Settings flags: [aqp/config/settings.py](../aqp/config/settings.py)
  "Orchestration control plane" block.
- Regression test: [tests/agents/test_orchestration_flags.py](../tests/agents/test_orchestration_flags.py).
- Adapter abstraction: `aqp/agents/orchestration/` (Phase 1).
- Adapters: `aqp/agents/orchestration/adapters/` (Phases 2-4).
- DataMCP tools: `aqp/data/mcp/tools/orchestration.py` + `automation.py` (Phase 3).
- Celery task: `aqp/tasks/orchestration_tasks.py` (Phase 3).
- Persistence: `aqp/persistence/models_workflows.py` + alembic `0046_workflow_versioning.py` (Phase 5).
- API: `aqp/api/routes/workflows.py` (Phase 5).
- Studio UI: `frontend/src/routes/workflows/*` (Phase 5).
- Halt + watchdog hardening: `aqp/tasks/agent_watchdog_tasks.py`, `frontend/src/components/common/KillSwitch.tsx` (Phase 6).
