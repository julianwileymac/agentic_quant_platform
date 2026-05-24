# AQP IDE quant widgets

Three quant-focused widgets shipped by
[`theia-ide-aqp-quant-ext`](../theia-extensions/aqp-quant/) that
complement (do NOT duplicate) the AQP Vite operator UI:

| Widget | Purpose | View id |
| --- | --- | --- |
| `SpecAuthorWidget` | JSON-schema editor for the 5 hash-locked spec runtimes | `aqp.quant.view.spec-author` |
| `RunInspectorWidget` | Live-tail of any runtime's `*_runs` ledger over WebSocket | `aqp.quant.view.run-inspector` |
| `BacktestRunnerWidget` | Single launcher that dispatches to the right `/runs` endpoint | `aqp.quant.view.backtest-runner` |

## SpecAuthorWidget

Kind dropdown — Agent / Bot / RL / Analysis / Workflow. Every save
snapshots a new immutable `*_spec_versions` row via the matching
`persist_spec` REST endpoint (hash-locked per AQP rules 13, 15, 17, 24,
41).

| Spec kind | Runtime | List | Get | Snapshot | Run |
| --- | --- | --- | --- | --- | --- |
| Agent | `AgentRuntime` | `GET /agents/specs` | `GET /agents/specs/{name}` | `POST /agents/specs` | `POST /agents/runs/v2` |
| Bot | `BotRuntime` | `GET /bots` | `GET /bots/{name}` | `POST /bots` | `POST /bots/runs` |
| RL | `RLRuntime` | `GET /rl/experiments` | `GET /rl/experiments/{name}` | `POST /rl/experiments` | `POST /rl/runs` |
| Analysis | `AnalysisRuntime` | `GET /analysis/specs` | `GET /analysis/specs/{name}` | `POST /analysis/specs` | `POST /analysis/runs` |
| Workflow | `WorkflowRuntime` | `GET /workflows` | `GET /workflows/{name}` | `POST /workflows` | `POST /workflows/runs` |

The widget never mutates an existing version row — a save with a
changed hash produces a new row, leaving the prior version intact for
replay (rule contract per the runtime).

## RunInspectorWidget

Paste a `task_id` (or have BacktestRunner attach one automatically),
press Attach. The widget opens a WebSocket to:

```
ws(s)://<aqp-api>/ws/tasks/{task_id}?token=<auth0-bearer>&X-AQP-Workspace=...
```

and renders every incoming frame using the canonical AQP progress shape
(rule 4):

```json
{
  "task_id": "abc-123",
  "stage": "training",
  "message": "Episode 42 / 1000",
  "timestamp": 1748097600.123,
  "step": 4200,
  "episode": 42,
  "mean_reward": 0.834
}
```

Browsers can't set `Authorization` headers on WebSocket handshakes, so
the bearer and tenancy headers are passed as query params. The AQP
backend's WebSocket handler reads them on the upgrade request and treats
them identically to header values for the rest of the connection.

## BacktestRunnerWidget

Single launcher that dispatches based on `target`:

| Target | Endpoint | Backed by AQP runtime |
| --- | --- | --- |
| Bot | `POST /bots/{ref}/backtest` | `BotRuntime` (rule 14) |
| Workflow | `POST /workflows/{name}/run` | `WorkflowRuntime` (rule 40) |
| RL Experiment | `POST /rl/runs` | `RLRuntime` (rule 16) |
| Analysis | `POST /analysis/runs` | `AnalysisRuntime` (rule 23) |

The widget does NOT pick an engine — engine selection comes from the
spec body (e.g. `RLExperimentSpec.engine`, `BotSpec.backtest.engine`).
This avoids duplicating AQP's 9-engine dispatcher inside the IDE.

After launch, the widget surfaces the returned `task_id` and an
"Attach Run Inspector" button that opens the `RunInspectorWidget` with
the task pre-attached.

## Hard-rule contract

| Rule | How the widget honours it |
| --- | --- |
| 2 (LLM gateway) | None of the widgets call LLMs directly. Spec-authoring AI assistance lives in the Research Copilot (rule 2 via `router_complete`). |
| 4 (progress frame) | `RunInspectorWidget` consumes the canonical `{task_id, stage, message, timestamp, **extras}` frame verbatim. |
| 13/15/17/24/41 (hash-locked specs) | `SpecAuthorWidget` always POSTs to the snapshot endpoint; the AQP backend creates a new version row when the hash changes. |
| 22 (DataMCP) | The widgets never query Iceberg / Postgres directly — only AQP REST. |
| 27 (IdentityProvider) | Every HTTP call goes through `AqpApiService` (Auth0 bearer + auto-refresh). |
| 51 (tenancy isolation) | Tenancy headers are attached by `AqpApiService` automatically. |

## What the widgets do NOT do

- Re-implement the AQP Vite operator dashboards. Open the Vite UI for
  rich charts, dashboards, and configuration screens. Open the Theia
  widgets for spec authoring + live run inspection while you code.
- Re-implement the kill-switch. That lives in `theia-ide-aqp-ext` with
  the `ctrlcmd+alt+h` shortcut and the 9-endpoint halt fan-out.
- Implement RTC (real-time collaboration). Deferred to a Phase B
  iteration; see [../../aqp_docs/aqp-ide-roadmap.md](../../aqp_docs/aqp-ide-roadmap.md).

## See also

- [extensions.md](extensions.md) — full extension reference
- `aqp_docs/agents.md`, `aqp_docs/bots.md`, `aqp_docs/rl-framework.md`,
  `aqp_docs/analysis-framework.md`, `aqp_docs/workflow-studio.md`
- `aqp/tasks/_progress.py` — canonical progress frame (rule 4)
