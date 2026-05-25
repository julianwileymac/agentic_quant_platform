---
title: 'Recipe: snapshot an agent spec'
summary: 'Hash-lock a YAML AgentSpec into agent_spec_versions so AgentRuntime can drive it.'
owner: agentic-team
last_reviewed: 2026-05-25
audience: both
---

# Recipe: snapshot an agent spec

```powershell
# Idempotent — re-running with unchanged content returns the same
# spec_hash and the same version row.
curl -X POST http://localhost:8000/agents/specs `
    -H "Content-Type: application/json" `
    -d @configs/agents/my-agent.yaml
```

The response carries `spec_hash` and `version`. If you change a
field and re-POST, a NEW `agent_spec_versions` row is created with
a NEW hash. Old versions stay intact for replay.

## What the runtime does

The
[`AgentRuntime`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/agents/runtime.py)
gates every run on:

- A valid `agent_spec_versions` row.
- A cost cap (`per_run_max_tokens`, `per_run_max_usd`).
- The active kill switch.
- The RFC 9728 + 8707 MCP audience check (rule 49).
- An `experiment_id` (rule 34).

If any check fails, the run rejects before the first LLM call.

## Run the agent

```powershell
curl -X POST http://localhost:8000/agents/<spec_name>/run `
    -d '{"inputs":{"universe":["SPY","QQQ","IWM"]}}'
```

`AgentRuntime` writes `agent_runs_v2` rows with telemetry, cost,
and OTEL trace IDs.

## Don't bypass the runtime

Never call `router_complete` directly from inside agent code. Declare
the model in `AgentSpec.model` and let the runtime drive the call.
See [AGENTS rule 12](https://github.com/julianwileymac/agentic_quant_platform/blob/main/AGENTS.md).

## Deeper reads

- [Concept: agents](../../concepts/agentic/agents.md)
- [Concept: agentic development](../../concepts/agentic/agentic-development.md)
- [Concept: workflow studio](../../concepts/agentic/workflow-studio.md)
- [Tutorial: first agent workflow](../../tutorials/first-agent-workflow.md)
