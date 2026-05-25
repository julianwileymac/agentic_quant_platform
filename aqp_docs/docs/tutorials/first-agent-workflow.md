---
title: 'Your first agent workflow'
summary: 'Compose a three-node LangGraph (Research / Selection / Trader), run it through AgentRuntime, inspect the agent_runs_v2 ledger.'
owner: agentic-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 5
---

# Your first agent workflow

Goal: stand up a three-node agentic loop driven by `WorkflowRuntime`,
see it through one complete iteration, inspect the immutable
`agent_runs_v2` rows it produces.

## Why

`AgentSpec` + `AgentRuntime` is AQP's "skill artifact" — every agent
run is hash-locked into `agent_spec_versions` and audited through
`agent_runs_v2`. Combined with the additive `WorkflowRuntime`
(orchestration adapter pattern), this is how AQP composes
multi-agent pipelines without losing replay or kill-switch
semantics. See [Concept: workflow studio](../concepts/agentic/workflow-studio.md).

## Step 1 — author the workflow

Create `configs/workflows/my_first_workflow.yaml`:

```yaml
name: MyFirstResearchLoop
adapter_kind: graph
nodes:
  - id: research
    agent_spec: configs/agents/research_lite.yaml
    inputs:
      universe: [SPY, QQQ, IWM]
      lookback_days: 30
  - id: selection
    agent_spec: configs/agents/selection_lite.yaml
    depends_on: [research]
  - id: trader
    agent_spec: configs/agents/trader_paper.yaml
    depends_on: [selection]
edges:
  - { from: research, to: selection }
  - { from: selection, to: trader }
cost_caps:
  per_node_max_tokens: 4000
  per_run_max_usd: 0.50
halt_check_seconds: 5
```

## Step 2 — snapshot + run

```powershell
curl -X POST http://localhost:8000/workflows/MyFirstResearchLoop/run \
    -d '{}'
```

`WorkflowRuntime`:

1. Hash-locks the spec into `workflow_spec_versions`.
2. Reads each referenced `AgentSpec` and hash-locks them into
   `agent_spec_versions`.
3. Begins traversing the DAG, calling each agent through
   `AgentRuntime`.
4. Emits canonical progress frames per AGENTS rule 4.
5. Writes `agent_runs_v2` and `workflow_runs` rows.

## Step 3 — watch the breadcrumbs

The operator UI renders the workflow live at
`/workflows/runs/<run_id>`. From the CLI:

```powershell
docker exec aqp-api python -c "from aqp.ws.broker import subscribe; \
    [print(m) for m in subscribe('<run_task_id>')]"
```

## Step 4 — inspect the ledger

```sql
SELECT id, workflow_name, status, started_at, ended_at, total_tokens, total_cost_usd
FROM workflow_runs ORDER BY started_at DESC LIMIT 1;

SELECT id, agent_name, node_id, status, total_tokens
FROM agent_runs_v2
WHERE workflow_run_id = '<from_above>'
ORDER BY started_at;
```

You should see three `agent_runs_v2` rows — one per node.

## Step 5 — replay

```powershell
curl -X POST http://localhost:8000/workflows/runs/<workflow_run_id>/replay
```

Same hash-locked spec versions, new run row.

## Step 6 — halt

The kill switch fans out:

```powershell
curl -X POST http://localhost:8000/workflows/halt
```

Every running workflow stops; `agent_runs_v2` rows close with
`status=halted`.

## Verify

- [ ] `workflow_spec_versions` row with a `spec_hash`.
- [ ] Three `agent_spec_versions` rows (one per node).
- [ ] One `workflow_runs` row + three `agent_runs_v2` rows.
- [ ] Total cost in USD <= `per_run_max_usd` from the spec.
- [ ] Replay produces a new `workflow_runs` row but reuses the
  same spec-version rows.

## What next

- [Concept: agentic pipeline](../concepts/agentic/agentic-pipeline.md) —
  the full five-stage lifecycle (models, data, snapshot, dispatch,
  review) and how this tutorial maps to it.
- [Concept: workflow studio](../concepts/agentic/workflow-studio.md) —
  the seven adapter kinds (graph / crew / debate / fusion /
  execution / schedule / studio).
- [Concept: multi-agent patterns](../concepts/agentic/multi-agent-patterns.md) —
  Sequential / Parallel / Debate / Coordinator / ReAct topologies.
- [Tutorial: first RL experiment](./first-rl-experiment.md) — hand
  RL outputs into an agent loop.
