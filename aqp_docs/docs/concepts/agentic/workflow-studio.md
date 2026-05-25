---
title: 'Workflow Studio'
summary: '| Layer | File / Path | | --- | --- | | Spec contract | [aqp/agents/orchestration/spec.py](../aqp/agents/orchestration/spec.py) | | Registry + persist_spec | [aqp/agents/orchestration/registry_specs.p...'
owner: agentic-team
last_reviewed: 2026-05-25
audience: both
---

# Workflow Studio

The Workflow Studio is the operator-facing surface for the additive
orchestration control plane introduced by the seven-phase refactor in
[orchestration-refactor-rollout.md](../../concepts/agentic/orchestration-refactor-rollout.md).
It composes the five existing graph builders, the three (then five)
adapters, and the new hash-locked `WorkflowSpec` registry into a
single replayable workflow concept.

## What ships

| Layer | File / Path |
| --- | --- |
| Spec contract | [aqp/agents/orchestration/spec.py](../aqp/agents/orchestration/spec.py) |
| Registry + persist_spec | [aqp/agents/orchestration/registry_specs.py](../aqp/agents/orchestration/registry_specs.py) |
| Runtime | [aqp/agents/orchestration/runtime.py](../aqp/agents/orchestration/runtime.py) |
| Adapter ABC + metaclass | [aqp/agents/orchestration/base.py](../aqp/agents/orchestration/base.py) |
| Adapter registry | [aqp/agents/orchestration/registry.py](../aqp/agents/orchestration/registry.py) |
| Adapters (5) | [aqp/agents/orchestration/adapters/](../aqp/agents/orchestration/adapters/) |
| ORM | [aqp/persistence/models_workflows.py](../aqp/persistence/models_workflows.py) |
| Migration | [alembic/versions/0046_workflow_versioning.py](../alembic/versions/0046_workflow_versioning.py) |
| REST | [aqp/api/routes/workflows.py](../aqp/api/routes/workflows.py) |
| Celery tasks | [aqp/tasks/orchestration_tasks.py](../aqp/tasks/orchestration_tasks.py) |
| DataMCP tools | [aqp/data/mcp/tools/orchestration.py](../aqp/data/mcp/tools/orchestration.py), [aqp/data/mcp/tools/automation.py](../aqp/data/mcp/tools/automation.py) |
| Cache entry | `workflows` category in [aqp/cache/keys.py](../aqp/cache/keys.py) |
| Frontend routes | [aqp_client/src/routes/workflows/](../aqp_client/src/routes/workflows/) |
| Frontend components | [aqp_client/src/components/workflows/](../aqp_client/src/components/workflows/) |

## Spec shape

A workflow selects exactly one
[`OrchestrationAdapter`](../aqp/agents/orchestration/base.py) by alias
and hands it adapter-specific params. The adapter dispatches
internally — composite flows (Crew + Graph + Debate) belong inside
their own adapter, not at the spec layer.

```yaml
name: research.dialectical_with_fusion_v1
description: "Bull/Bear debate + fusion + weight-centric execution"
adapter: LangGraphAdapter
adapter_kind: graph
params:
  builder: dialectical          # one of build_* in aqp/agents/graph/
  builder_kwargs:
    max_rounds: 2
schedule:
  cron: "30 13 * * 1-5"
  timezone: UTC
  enabled: false                # operator flips after the studio + schedule flags
guardrails:
  cost_budget_usd: 3.0
  max_calls: 60
  max_duration_seconds: 900
annotations: [research, dialectical]
template_target: research
```

`WorkflowSpec.snapshot_hash()` is the SHA256 of the canonical JSON
form (sorted keys, no whitespace). Re-snapshotting a spec with the
same hash returns the existing `workflow_spec_versions` row;
changing any field inserts a NEW row (parallel to
`agent_spec_versions`, `bot_versions`, `rl_experiment_versions`,
`analysis_spec_versions`).

## Operator flow

1. Operator flips `AQP_ORCHESTRATION_STUDIO_ENABLED=true` (see the
   rollout doc).
2. Frontend navigates to `/workflows`. List + detail render through
   `<EntityPicker kind="workflows" />` so the dropdown shares the
   same cache invalidation path as every other entity picker.
3. Operator hits **Run** → POST `/workflows/{name}/run` → enqueues
   `aqp.tasks.orchestration_tasks.run_workflow`. The route returns a
   `task_id`; the studio attaches via the existing `useLiveStream`
   hook for `_progress.emit` frames (rule 4).
4. Operator hits **Replay** on a historical run → POST
   `/workflows/runs/{run_id}/replay` re-dispatches with the
   captured `spec_version_id` for deterministic reproduction.
5. Operator hits the topbar KillSwitch's "Halt workflows" action →
   POST `/workflows/halt` mirrors the five canonical halt endpoints
   (`/agents/halt`, `/paper/stop-all`, `/bots/halt-all`,
   `/rl/halt-all`, `/quant-agents/halt`).

## Halt fan-out

The Phase 2 `WorkflowRuntime` checks `should_halt(state)` between
every adapter transition. `should_halt` is the OR of:

- `has_kill_switch()` — Redis-backed global flag (the existing
  topbar KillSwitch flips this).
- `state["halt_token"]` — per-run boolean the Phase 6
  `/workflows/halt` endpoint sets on every active `WorkflowRun` row
  inside `AQP_ORCHESTRATION_HALT_CHECK_TIMEOUT_SECONDS` of the API
  call.

Long-running adapters (`CrewProcessAdapter`, `LangGraphAdapter`,
`DialecticalDebateAdapter`) poll `context.is_halted()` between
inner steps so the SLA holds even mid-debate.

## Adapter catalog (Phases 2-5)

| alias | kind | source | when registered |
| --- | --- | --- | --- |
| `LangGraphAdapter` | graph | aqp | always |
| `CrewProcessAdapter` | crew | finrobot | always (gated invoke) |
| `DialecticalDebateAdapter` | debate | tradingagents | always |
| `AutomationScheduleAdapter` | schedule | daily_stock_analysis | always (gated invoke) |
| `SignalFusionAdapter` | fusion | vibe_trading | always (gated invoke) |
| `WeightCentricExecutionAdapter` | execution | finrl | always (gated invoke) |
| `WorkflowStudioAdapter` (Phase 7) | studio | langflow | TBD |

New adapters land by subclassing
[`OrchestrationAdapter`](../aqp/agents/orchestration/base.py) and
setting `adapter_kind` + `adapter_alias`. The metaclass auto-registers
them through
[`aqp.core.registry.register`](../aqp/core/registry.py) and the
shadow per-kind index in
[`aqp/agents/orchestration/registry.py`](../aqp/agents/orchestration/registry.py).

## Audit trail

Every run produces:

- A `workflow_runs` row (one per run) with `spec_version_id`,
  `inputs`, `final_state`, `breadcrumbs`, `experiment_id`, `test_id`
  (rule 34), `cost_usd`, `duration_ms`, `status`, `halted`, `error`.
- A series of `_progress.emit` frames the studio streams live
  through `useLiveStream` (frame shape per rule 4).
- Per-adapter `node_span` OTEL spans emitted by
  [`aqp/agents/observability.py`](../aqp/agents/observability.py).
- Optional `agent_runs_v2` rows for each inner `AgentRuntime` call
  the wrapped adapter makes.

## Replay semantics

`POST /workflows/runs/{run_id}/replay` looks up the matching
`workflow_runs` row, hydrates the frozen
`workflow_spec_versions.payload`, and re-dispatches with the same
inputs. Replay produces a NEW `workflow_runs` row tagged with the
original run's id in `parent_run_id` so the trace lineage stays
intact.

## See also

- [orchestration-refactor-rollout.md](../../concepts/agentic/orchestration-refactor-rollout.md) — operator runbook + per-flag rollback.
- [multi-agent-patterns.md](../../concepts/agentic/multi-agent-patterns.md) — the seven adapter topologies (Phase 7 docs update).
- [data-mcp.md](../../concepts/data/data-mcp.md) — `data.orchestration.*` and `data.automation.*` tool catalog.
- [agentic-development.md](../../concepts/agentic/agentic-development.md) — where `WorkflowSpec` sits in the four-runtime + skill-artifact framework.
