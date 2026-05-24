# Agent stall watchdog (Phase 5)

The agent stall watchdog is a Celery beat task that scans
`agent_runs_v2` for rows the runtime will never close — Celery
dispatch dropped (`status='pending'` forever) or the runtime hung
mid-tool-loop without inserting any `agent_run_steps` heartbeat.

## Why

Today nothing on the AQP side polls for stalled runs. Operators
only notice when the topbar counters stay stuck. The watchdog gives
us a deterministic cleanup pass + a `GET /agents/health` snapshot the
frontend can render.

## What it does

For every `agent_runs_v2` row with `status in ('running','pending')`:

- **pending longer than `2 × settings.agent_stall_threshold_seconds`**
  → halt.
- **running with no new `agent_run_steps` insert in the last
  `settings.agent_stall_threshold_seconds`** → halt.

For each halted row:

1. `app.control.revoke(task_id, terminate=True, signal='SIGTERM')`
2. Update the row in-place: `status='halted'`,
   `error='watchdog:stalled'`, `completed_at=now()`.
3. `_progress.emit_done(task_id, {halted: true, reason: 'watchdog:stalled'})`

Read-only health snapshots (`GET /agents/health`) return:

```json
{
  "running": 7,
  "pending": 2,
  "halted_last_24h": 3,
  "stalled_candidates": [
    {
      "run_id": "abc…",
      "spec": "alpha_researcher",
      "started_at": "…",
      "task_id": "…",
      "stalled_seconds": 412,
      "status": "running"
    }
  ],
  "stall_threshold_seconds": 300,
  "last_watchdog_at": "…"
}
```

## Settings

| Name | Default | Purpose |
|------|---------|---------|
| `AQP_AGENT_STALL_THRESHOLD_SECONDS` | 300 | running-row stall threshold |
| `AQP_AGENT_WATCHDOG_ENABLED` | true | global on/off |
| `AQP_AGENT_WATCHDOG_PERIOD_SECONDS` | 60 | celery beat interval |

## Hard rules

- **Rule 4 (Celery progress).** Every emit goes through
  [`_progress.emit_done`](../aqp/tasks/_progress.py). No direct
  Redis publishes.
- **Rule 12 (AgentRuntime).** The watchdog **never** constructs an
  `AgentRuntime`. It only flips status on the row and revokes the
  Celery dispatch.
- **Rule 22 (DataMCP).** Agents reach the snapshot through
  `data.agents.health` ([aqp/data/mcp/tools/agents.py](../aqp/data/mcp/tools/agents.py)).
- **Rule 13 (hash lock).** `agent_spec_versions` is immutable; the
  watchdog never touches it.

## Frontend

`/agents/health` page polls every 5s, surfaces counters + stalled
list. The matching mutating action is the existing
`POST /agents/halt` already wired through the topbar kill-switch.

## Companion: the GPT-5.5 monitor subagent

The Cursor subagent
[`.cursor/agents/aqp-run-monitor.md`](../.cursor/agents/aqp-run-monitor.md)
is the agentic-coding companion to this Celery watchdog: it monitors
the **Code-5.3 implementer subagents** themselves (the parent's
work runs) and nudges or restarts stalled workers. The two layers
are intentionally separate — one watches the AQP runtime, the other
watches the IDE workflow.
