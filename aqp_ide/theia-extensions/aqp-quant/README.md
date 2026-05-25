# theia-ide-aqp-quant-ext

AQP quant widgets that complement the Vite operator UI: SpecAuthor (for
the five hash-locked spec runtimes), RunInspector (canonical progress
frame, rule 4), and BacktestRunner (single launcher dispatching to the
right AQP REST endpoint).

## Widgets

| Widget | Wraps | View id |
| --- | --- | --- |
| `SpecAuthorWidget` | `GET /agents/spec-schema`, `POST /agents/specs`, and the four sibling routes for bots / rl / analysis / workflows | `aqp.quant.view.spec-author` |
| `RunInspectorWidget` | WebSocket `/ws/tasks/{task_id}` (canonical frame, rule 4) + REST snapshots for runtimes that don't stream | `aqp.quant.view.run-inspector` |
| `BacktestRunnerWidget` | Dispatches to `/bots/{ref}/backtest`, `/workflows/{name}/run`, `/rl/runs`, `/analysis/runs`, or legacy `/backtest/*` based on the picked spec | `aqp.quant.view.backtest-runner` |

## What this extension does NOT do

- Re-implement the AQP Vite operator dashboards (kept in `aqp_client/`).
- Pick a backtest engine. Engine selection comes from the spec.
- Mutate existing `*_spec_versions` rows. Every save snapshots a new row
  via the AQP backend's `persist_spec` hash-lock.

## Files

- [src/browser/aqp-quant-frontend-module.ts](src/browser/aqp-quant-frontend-module.ts)
- [src/browser/services/aqp-runtime-client.ts](src/browser/services/aqp-runtime-client.ts)
- [src/browser/services/aqp-ws-client.ts](src/browser/services/aqp-ws-client.ts)
- [src/browser/widgets/spec-author-widget.tsx](src/browser/widgets/spec-author-widget.tsx)
- [src/browser/widgets/run-inspector-widget.tsx](src/browser/widgets/run-inspector-widget.tsx)
- [src/browser/widgets/backtest-runner-widget.tsx](src/browser/widgets/backtest-runner-widget.tsx)
- [src/browser/commands/aqp-quant-view-contributions.ts](src/browser/commands/aqp-quant-view-contributions.ts)
- [src/common/aqp-quant-protocol.ts](src/common/aqp-quant-protocol.ts)

## See also

- [../../docs/quant-widgets.md](../../docs/quant-widgets.md)
- `aqp_docs/docs/concepts/agentic/agents.md`, `aqp_docs/docs/concepts/agentic/bots.md`, `aqp_docs/docs/concepts/rl/rl-framework.md`,
  `aqp_docs/docs/concepts/strategy/analysis-framework.md`, `aqp_docs/docs/concepts/agentic/workflow-studio.md`
