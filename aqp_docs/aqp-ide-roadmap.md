# AQP IDE roadmap

This doc maps the [external quant-IDE
blueprint](https://github.com) (compressed: "Bloomberg-grade research
IDE you can own", 12–18 month Phase 1/2/3 plan) to AQP's existing
architecture and the 55 hard rules.

## Why we deviate from the blueprint

The blueprint targets greenfield buyers of a quant PaaS. AQP already
has:

- Five hash-locked spec runtimes (`AgentSpec` / `BotSpec` /
  `RLExperimentSpec` / `AnalysisSpec` / `WorkflowSpec`) — rules
  12-13, 14-15, 16-17, 23-25, 40-41.
- Nine backtest engines (vbt-pro, event-driven, OSS vectorbt,
  backtesting.py, LEAN, ZVT, AAT, hftbacktest, NautilusTrader bridge).
- DataMCP + CodebaseMCP — rule 22, exposed over RFC 9728 / RFC 8707
  conformant streamable HTTP per rule 49.
- AlphaVantage / IBKR / Alpaca brokers — paper trading exists.
- Iceberg lakehouse with medallion-tier business metadata — rule 21.
- A Vite 7 + React 19 operator UI (`aqp_client/`) that already covers
  the operator dashboard scope.

The IDE's role in AQP is **the developer / research environment** —
notebook + MCP copilot + spec authoring + repo navigation. It does NOT
re-implement what `aqp_client/` already does well.

## Phasing

### Phase A — Shipped in this enhancement

| Workstream | Blueprint section | AQP-aligned implementation |
| --- | --- | --- |
| Six compile-time Theia extensions | §2.2 + §2.5 + §2.6 + §2.8 | `aqp-ext`, `aqp-shell-ext`, `aqp-mcp-bridge-ext`, `aqp-research-copilot-ext`, `aqp-notebook-quant-ext`, `aqp-quant-ext` |
| FINOS Perspective notebook renderer | §2.6 + §4.5 | `aqp-notebook-quant-ext`'s `PerspectiveArrowRenderer` (lazy-loads `@finos/perspective`) |
| MCP-driven research copilot | §2.7 + §5.4 | `aqp-research-copilot-ext`'s `AqpResearchAgent` (routes through `router_complete`, rule 2) |
| White-label shell + filters | §2.8 | `aqp-shell-ext`'s `FilterContribution` + window title + about dialog |
| Quant widgets (operator complement) | §5.1 | `aqp-quant-ext`'s SpecAuthor + RunInspector + BacktestRunner |
| `aqp-cli ide` entrypoint | (CLI orchestration) | `install` / `build` / `start` / `stop` / `status` / `logs` / `open` / `url` / `env` / `detect` / `doctor` |
| Single-pod K8s manifests | §7 (Layer 2) | `aqp_platform/deployments/kubernetes/aqp-ide/` |
| Theia Cloud Phase B scaffolding | §3 | `aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/` with `DEFERRED.md` |
| Per-extension AGENTS + READMEs + skills + rules | (governance) | 6 README + 6 AGENTS + 2 skills + 1 rule + 2 subagents |
| Workspace retirement checklist | (governance) | `aqp_ide/docs/retire-vendored-workspace.md` |

### Phase B — Trigger: ≥2 internal users need isolated workspaces

| Workstream | Blueprint section | AQP-aligned implementation |
| --- | --- | --- |
| Theia Cloud multi-tenant operator | §3 | Install upstream `theia-cloud` Helm + apply the `AppDefinition` scaffolded under `aqp-ide/theia-cloud/` |
| Per-tenant PVC + workspace | §3.5 | One PVC per `Workspace.theia.cloud/v1beta5` |
| Activity-tracker idle shutdown | §3.3 | `monitor.activityTracker.timeoutAfter` on `AppDefinition` |
| Private Open VSX mirror | §2.9 | Self-hosted Open VSX in `aqp-ide` namespace |
| Step-up confirmation for copilot write tools | (rule 52) | Surface confirmation chips before invoking `/halt` / `/me/byok/*` / `/tenancy/invites` tools |

### Phase C — Trigger: tick / order-book research demand emerges

| Workstream | Blueprint section | AQP-aligned implementation |
| --- | --- | --- |
| Arrow Flight gateway backend service | §4.1 | A new compile-time extension `aqp-flight-gateway-ext` with a JSON-RPC service that fronts AQP Iceberg + Snowflake (when present) via ADBC |
| Tick blotter widget | §5.2 | New widget in `aqp-quant-ext` (or a sibling `aqp-trading-ext`) that subscribes to the live market data Kafka topic |
| Real-time Yjs notebook collaboration | §5.5 | New compile-time extension `aqp-notebook-rtc-ext` with a backend Yjs WebSocket server |
| Hudi upsert-heavy market-data partitions | (rule 46) | Wire `aqp/data/lakehouse/hudi/` into the BacktestRunner spec UI |
| GPU / RAPIDS scheduling | §3 (Layer 5) | New `AppDefinition` flavour with GPU node selectors |

## Hard-rule mapping summary

| Rule | Phase A | Phase B | Phase C |
| --- | --- | --- | --- |
| 2 (LLM gateway) | Copilot uses `router_complete` | (no change) | Hudi-aware code samples in copilot |
| 4 (progress frame) | `AqpWsClient` consumes canonical frame | (no change) | (no change) |
| 22 (DataMCP) | MCP bridge | (no change) | Flight gateway uses DataMCP for catalog metadata |
| 26 (CredentialResolver) | Python helpers | (no change) | Flight gateway pulls Snowflake creds via store |
| 27 (IdentityProvider) | All extensions | Per-pod oauth2-proxy | (no change) |
| 45 (WorkloadRuntime) | CLI `doctor` + `aqp-ext` halt | Multi-pod halt via `/workloads/halt` | (no change) |
| 47 (topology) | CLI `detect` / `env` | (no change) | (no change) |
| 49 (MCP audience) | Bridge sets `X-AQP-MCP-Audience` | (no change) | (no change) |
| 52 (step-up MFA) | `aqp-ext` halt | Copilot write-tool gating | (no change) |

## Decision log

| Decision | Rationale |
| --- | --- |
| Use AQP `router_complete` (rule 2) for the copilot, NOT `@theia/ai-openai` / `@theia/ai-anthropic` etc. | AQP's provider catalog + cost caps + tenancy + audit run through `router_complete`. Bypassing it would create an auditing blind spot for every chat completion. |
| Use AQP's five spec runtimes for SpecAuthor, NOT a generic `BacktestService` JSON-RPC | The blueprint's hypothetical `BacktestService` is what AQP already has — five hash-locked spec runtimes with `persist_spec` + immutable version rows. Reinventing them would create a fork. |
| Defer Arrow Flight + Theia Cloud + RTC to Phase B/C | AQP's current load (single-tenant Vite UI + AQP API) does not justify the multi-tenant Theia Cloud operator yet. The blueprint's Flight gateway is a Phase C target — DataMCP + Iceberg already cover the data plane for Phase A. |
| Keep `aqp_client/` as the operator UI; Theia complements it | The Vite app already has the operator dashboards. Theia adds notebook + MCP copilot + spec authoring + repo navigation. Two surfaces, one tenancy, no duplication. |
| Make `aqp-cli ide` the canonical entrypoint | Production deploys go through one command. `yarn` stays for inner-loop dev. Mirrors the `aqp-cli client` pattern for the Vite frontend. |
| Don't fork Theia | Every blueprint risk register flags forking as catastrophic. AQP stays on community releases and adds via compile-time extensions only. |

## What this roadmap is NOT

- A commitment to ship every blueprint phase.
- A timeline. We ship Phase A now; Phase B and C ship when triggered.
- A justification for re-implementing what `aqp_client/` already provides.
- A reason to bypass the 55 hard rules.

## Source of truth

- The blueprint we summarised: external research report + product
  blueprint provided as the source for this enhancement.
- AQP's canonical hard rules: [../AGENTS.md](../AGENTS.md).
- Per-extension contracts:
  [../aqp_ide/theia-extensions/](../aqp_ide/theia-extensions/).
