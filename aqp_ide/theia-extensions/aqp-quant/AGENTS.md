# AGENTS.md

Agent contract for `theia-ide-aqp-quant-ext`.

## Purpose

Three quant-focused widgets that complement (do NOT duplicate) the AQP Vite
operator UI:

1. **SpecAuthorWidget** — JSON-schema-driven editor for the five hash-locked
   spec runtimes (`AgentSpec` / `BotSpec` / `RLExperimentSpec` /
   `AnalysisSpec` / `WorkflowSpec`). Saves snapshot a new immutable
   `*_spec_versions` row via the matching `persist_spec` REST endpoint.
2. **RunInspectorWidget** — live-tail of any runtime's `*_runs` ledger
   over WebSocket honouring the canonical AQP progress frame shape
   `{task_id, stage, message, timestamp, **extras}` (rule 4).
3. **BacktestRunnerWidget** — single launcher that dispatches to the
   right AQP REST endpoint based on the user's choice: `/bots/{ref}/backtest`,
   `/workflows/{name}/run`, `/rl/runs`, `/analysis/runs`, or the legacy
   `/backtest/*` shortcuts. Engine selection comes from the spec; the
   widget itself does NOT pick an engine.

## Hard boundaries

1. All HTTP through `AqpApiService` from `theia-ide-aqp-ext` — never
   instantiate `fetch` directly.
2. WebSocket subscriptions go through `AqpWsClient` (in this package),
   which honours the canonical progress frame (rule 4) and reuses
   `Auth0Service.getAccessToken()` for the bearer.
3. SpecAuthorWidget never mutates an existing version row. Saves produce a
   new row via the AQP backend's `persist_spec` hash-lock (rules 13, 15,
   17, 24, 41).
4. BacktestRunnerWidget never re-implements an engine. It dispatches.
5. Cross-extension dependency on `theia-ide-aqp-ext` is allowed; the
   reverse direction is forbidden.
6. No `import` from `agentic_quant_platform` source. Cross HTTP only.

## Validation

```bash
yarn build:extensions
yarn build:applications:dev
```

After build, verify in the running IDE:
- `View → AQP → Author Spec` opens SpecAuthorWidget, kind dropdown lists
  Agent / Bot / RL / Analysis / Workflow.
- `View → AQP → Inspect Run` opens RunInspectorWidget; pasting a
  `task_id` from a live agent run streams frames in.
- `View → AQP → Run Backtest` opens BacktestRunnerWidget; selecting a
  bot ref + clicking Run dispatches to `POST /bots/{ref}/backtest`.
