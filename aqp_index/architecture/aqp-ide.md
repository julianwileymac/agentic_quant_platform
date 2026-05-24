# AQP IDE

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: Phase A
> AQP IDE landing — six compile-time Theia extensions + `aqp-cli ide`
> entrypoint + single-pod K8s overlay).

SSoT pointer hub for the AQP IDE. The IDE is a cross-package surface:
the extensions live in [`aqp_ide/`](../../aqp_ide/), the operator
entrypoint in [`aqp_cli/`](../../aqp_cli/), the K8s overlay in
[`aqp_platform/`](../../aqp_platform/), the canonical docs pair in
[`aqp_docs/`](../../aqp_docs/), and the Python notebook helpers in
[`aqp/notebook/`](../../aqp/notebook/). That is why this concept has its
own architecture pointer (rule: a dedicated file is justified when a
concept crosses ≥3 `aqp_*` packages).

## Canonical sources (read these, never copy from them)

| Surface | Canonical doc | Hard rule(s) |
| --- | --- | --- |
| Monorepo SSoT pointer | [../../aqp_docs/aqp-ide.md](../../aqp_docs/aqp-ide.md) | AGENTS root project map row for `aqp_ide/` |
| Phased roadmap | [../../aqp_docs/aqp-ide-roadmap.md](../../aqp_docs/aqp-ide-roadmap.md) | – |
| In-folder index | [../../aqp_ide/AGENTS.md](../../aqp_ide/AGENTS.md) + [../../aqp_ide/docs/index.md](../../aqp_ide/docs/index.md) | – |
| Process + extension architecture | [../../aqp_ide/docs/architecture.md](../../aqp_ide/docs/architecture.md) | – |
| Per-extension reference | [../../aqp_ide/docs/extensions.md](../../aqp_ide/docs/extensions.md) | – |
| CLI cookbook | [../../aqp_ide/docs/cli-entrypoint.md](../../aqp_ide/docs/cli-entrypoint.md) + [../../aqp_cli/docs/index.md](../../aqp_cli/docs/index.md) | – |
| MCP wiring | [../../aqp_ide/docs/mcp-integration.md](../../aqp_ide/docs/mcp-integration.md) | AGENTS rules 22, 49 |
| Research copilot | [../../aqp_ide/docs/research-copilot.md](../../aqp_ide/docs/research-copilot.md) | AGENTS rule 2 |
| Notebook (Perspective MIME) | [../../aqp_ide/docs/notebook.md](../../aqp_ide/docs/notebook.md) | AGENTS rule 26 |
| Quant widgets | [../../aqp_ide/docs/quant-widgets.md](../../aqp_ide/docs/quant-widgets.md) | AGENTS rules 4, 13, 15, 17, 24, 41 |
| Deployment | [../../aqp_ide/docs/deployment.md](../../aqp_ide/docs/deployment.md) | – |
| Vendored-workspace retirement | [../../aqp_ide/docs/retire-vendored-workspace.md](../../aqp_ide/docs/retire-vendored-workspace.md) | – |
| Always-on rule | [../../.cursor/rules/aqp-ide.mdc](../../.cursor/rules/aqp-ide.mdc) | – |
| MCP-scoped rule | [../../aqp_ide/.cursor/rules/aqp-ide-mcp.mdc](../../aqp_ide/.cursor/rules/aqp-ide-mcp.mdc) | AGENTS rules 22, 49 |

## The six compile-time Theia extensions

| Extension package | Path | Frontend module | Purpose |
| --- | --- | --- | --- |
| `theia-ide-aqp-ext` | [../../aqp_ide/theia-extensions/aqp/](../../aqp_ide/theia-extensions/aqp/) | `lib/browser/aqp-frontend-module` | Auth0 PKCE login, five operator widgets, nine-endpoint kill-switch, tenancy QuickPick, `GET /aqp/config` Node endpoint |
| `theia-ide-aqp-shell-ext` | [../../aqp_ide/theia-extensions/aqp-shell/](../../aqp_ide/theia-extensions/aqp-shell/) | `lib/browser/aqp-shell-frontend-module` | White-label theme, `FilterContribution` lockdown, window-title + About-dialog rebinds |
| `theia-ide-aqp-mcp-bridge-ext` | [../../aqp_ide/theia-extensions/aqp-mcp-bridge/](../../aqp_ide/theia-extensions/aqp-mcp-bridge/) | `lib/browser/aqp-mcp-bridge-frontend-module` | Pre-configures `@theia/ai-mcp` for `aqp-data-mcp` + `aqp-codebase-mcp` (AGENTS rule 49) |
| `theia-ide-aqp-research-copilot-ext` | [../../aqp_ide/theia-extensions/aqp-research-copilot/](../../aqp_ide/theia-extensions/aqp-research-copilot/) | `lib/browser/aqp-research-copilot-frontend-module` | Theia AI `ChatAgent` routed through `router_complete` (AGENTS rule 2), spec-authoring prompts, AQP REST tool functions |
| `theia-ide-aqp-notebook-quant-ext` | [../../aqp_ide/theia-extensions/aqp-notebook-quant/](../../aqp_ide/theia-extensions/aqp-notebook-quant/) | `lib/browser/aqp-notebook-quant-frontend-module` + `lib/node/aqp-notebook-quant-backend-module` | FINOS Perspective MIME renderer for Arrow + `File → New AQP Notebook` scaffolder |
| `theia-ide-aqp-quant-ext` | [../../aqp_ide/theia-extensions/aqp-quant/](../../aqp_ide/theia-extensions/aqp-quant/) | `lib/browser/aqp-quant-frontend-module` | SpecAuthor + RunInspector (rule 4) + BacktestRunner widgets |

Dependency direction inside the IDE bundle:

```
aqp-ext  <-- aqp-shell-ext
   ^
   +------ aqp-mcp-bridge-ext  <-- aqp-research-copilot-ext
   ^
   +------ aqp-notebook-quant-ext
   ^
   +------ aqp-quant-ext
```

Wired into the browser app via
[../../aqp_ide/applications/browser/package.json](../../aqp_ide/applications/browser/package.json)
+ runtime env block in
[../../aqp_ide/browser.Dockerfile](../../aqp_ide/browser.Dockerfile).

## Cross-package surfaces

| Surface | Lives in | Purpose |
| --- | --- | --- |
| `aqp-cli ide` command group | [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) + `AQP_CLI_THEIA_*` settings in [`aqp_cli/src/aqp_cli/config.py`](../../aqp_cli/src/aqp_cli/config.py) | Canonical production entrypoint (install / build / start / stop / status / logs / open / url / env / detect / doctor) |
| `aqp/notebook/` Python helpers | [`aqp/notebook/__init__.py`](../../aqp/notebook/__init__.py) + [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) | Kernel-side `attach()` / `AqpNotebookContext` — consumed by the notebook scaffolder cell |
| Single-pod K8s overlay | [`aqp_platform/deployments/kubernetes/aqp-ide/`](../../aqp_platform/deployments/kubernetes/aqp-ide/) | namespace + configmap + secret-template + deployment + service + ingress + networkpolicy. Phase B Theia Cloud scaffolding under [`theia-cloud/`](../../aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/). |
| Docker image | [`aqp_ide/browser.Dockerfile`](../../aqp_ide/browser.Dockerfile) | Multi-arch, hosts the `AQP_THEIA_*` runtime env block read by `aqp-config-endpoint.ts` |

## AGENTS rules surfaced by the IDE

The IDE is a transcript surface for these hard rules. The IDE side
*honours* the rule; the AQP backend side *enforces* it.

| Rule | What the IDE side does | Where in `aqp_ide/` |
| --- | --- | --- |
| 2 (LLM gateway) | `RouterCompleteClient` is the only LLM caller; vendor SDK adapters are forbidden | [`aqp-research-copilot/src/browser/copilot/router-complete-client.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/router-complete-client.ts) |
| 4 (canonical progress frame) | `AqpWsClient` consumes `{task_id, stage, message, timestamp, **extras}` verbatim | [`aqp-quant/src/browser/services/aqp-ws-client.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-ws-client.ts) |
| 22 (DataMCP boundary) | The bridge is the only programmatic consumer of `MCPServerManager.addOrUpdateServer(...)` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) |
| 26 (CredentialResolver) | Notebook helpers route through `CredentialResolver` (never hand-roll a vendor auth flow) | [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) |
| 27 (IdentityProvider) | `Auth0Service` is the sole identity surface inside Theia | [`aqp/src/browser/auth/auth0-service.ts`](../../aqp_ide/theia-extensions/aqp/src/browser/auth/auth0-service.ts) |
| 45 (WorkloadRuntime) | `aqp-cli ide doctor` + the nine-endpoint kill-switch fan-out | [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) + [`aqp/src/browser/commands/aqp-halt-contribution.ts`](../../aqp_ide/theia-extensions/aqp/src/browser/commands/aqp-halt-contribution.ts) |
| 47 (topology) | `aqp-cli ide url --remote` + `detect` + `env` look up topology services | [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) |
| 49 (MCP audience) | Bridge mints per-MCP `aud` tokens; sets non-secret `X-AQP-MCP-Audience` header | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) |
| 52 (step-up MFA) | Halt commands + (Phase B) copilot write-tool confirmation chips | [`aqp/src/browser/commands/aqp-halt-contribution.ts`](../../aqp_ide/theia-extensions/aqp/src/browser/commands/aqp-halt-contribution.ts) |

## Cursor governance

| Artefact | Path |
| --- | --- |
| Always-on rule | [`.cursor/rules/aqp-ide.mdc`](../../.cursor/rules/aqp-ide.mdc) |
| MCP-scoped rule | [`aqp_ide/.cursor/rules/aqp-ide-mcp.mdc`](../../aqp_ide/.cursor/rules/aqp-ide-mcp.mdc) |
| Quant-author subagent | [`.cursor/agents/aqp-ide-quant-author.md`](../../.cursor/agents/aqp-ide-quant-author.md) |
| IDE-docs curator subagent | [`aqp_ide/.cursor/agents/aqp-ide-curator.md`](../../aqp_ide/.cursor/agents/aqp-ide-curator.md) |
| Quant-widget skill | [`aqp_ide/.cursor/skills/aqp-quant-widget/SKILL.md`](../../aqp_ide/.cursor/skills/aqp-quant-widget/SKILL.md) |
| MCP-wiring skill | [`aqp_ide/.cursor/skills/aqp-mcp-wiring/SKILL.md`](../../aqp_ide/.cursor/skills/aqp-mcp-wiring/SKILL.md) |
