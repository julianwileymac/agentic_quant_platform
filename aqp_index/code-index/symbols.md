# Public symbol catalog

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — first signature-populated section covers the six new
> Theia extensions, the updated AQP extension protocol + config
> endpoint, and `aqp/notebook/`).
>
> This file is curator-generated. See [index.md](index.md) for the
> methodology. Humans must not edit this file by hand.

## Coverage targets

The curator MUST emit:

- One subsection per `aqp_*` package's public surface.
- Cross-references for symbols that appear in
  [../../AGENTS.md](../../AGENTS.md)'s "Quick reference" table.
- A backlink to the source file at line precision (`path:line`).

Current population:

- `aqp/` — partial (`aqp/notebook/` only).
- `aqp_cli/` — partial (`commands/ide.py` + `config.py` IDE-related fields).
- `aqp_ide/theia-extensions/aqp*/` — populated for all six extensions.
- All other top-level packages — *pending*.

---

## `aqp.notebook` (Python public surface)

| Symbol | Source | Summary |
| --- | --- | --- |
| `aqp.notebook.attach(*, org, team, workspace, project, lab) -> AqpNotebookContext` | [`aqp/notebook/helpers.py:229`](../../aqp/notebook/helpers.py) | Build an `AqpNotebookContext` for the active tenancy; each kwarg defaults to the matching `AQP_*` env var. |
| `aqp.notebook.AqpNotebookContext` (`@dataclass`) | [`aqp/notebook/helpers.py:41`](../../aqp/notebook/helpers.py) | Composite handle exposing `data` / `codebase` / `router` / `perspective(table)` / `tenancy_summary()`. |
| `AqpNotebookContext.data` (property) | [`aqp/notebook/helpers.py:68`](../../aqp/notebook/helpers.py) | DataMCP-backed catalog client (lazy). |
| `AqpNotebookContext.codebase` (property) | [`aqp/notebook/helpers.py:80`](../../aqp/notebook/helpers.py) | CodebaseMCP-backed search / navigation client (lazy). |
| `AqpNotebookContext.router` (property) | [`aqp/notebook/helpers.py:87`](../../aqp/notebook/helpers.py) | `router_complete` LLM gateway facade (AGENTS rule 2). |
| `AqpNotebookContext.perspective(table)` | [`aqp/notebook/helpers.py:109`](../../aqp/notebook/helpers.py) | Serialise an Arrow `Table` into the AQP Perspective MIME envelope (`application/vnd.aqp.perspective-arrow+arrow`). |
| `AqpNotebookContext.tenancy_summary() -> str` | [`aqp/notebook/helpers.py:94`](../../aqp/notebook/helpers.py) | Redacted one-line description of the active tenancy. |

## `aqp_cli.commands.ide` (Typer command group)

The canonical operator entrypoint for the AQP IDE.

| Subcommand | Source | Summary |
| --- | --- | --- |
| `aqp-cli ide install [--frozen-lockfile]` | [`commands/ide.py:128`](../../aqp_cli/src/aqp_cli/commands/ide.py) | `yarn install` inside `aqp_ide/`. |
| `aqp-cli ide build [--dev/--prod]` | [`commands/ide.py:147`](../../aqp_cli/src/aqp_cli/commands/ide.py) | `yarn build:extensions` then `build:applications[:dev]`. |
| `aqp-cli ide start [--background] [--port N] [--workspace P] [--open]` | [`commands/ide.py:170`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Spawn Theia + persist pid/port to state file. |
| `aqp-cli ide stop` | [`commands/ide.py:254`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Stop the backgrounded Theia. |
| `aqp-cli ide status` | [`commands/ide.py:262`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Print pid / port / log path / URL. |
| `aqp-cli ide logs [--lines N]` | [`commands/ide.py:277`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Tail `ide.log`. |
| `aqp-cli ide open [--no-browser]` | [`commands/ide.py:290`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Open the IDE URL in the default browser. |
| `aqp-cli ide url [--remote]` | [`commands/ide.py:310`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Print local OR `--remote` cluster URL (via control-plane topology). |
| `aqp-cli ide env [--write PATH]` | [`commands/ide.py:357`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Render the `AQP_THEIA_*` env block; resolves from env + topology snapshot. |
| `aqp-cli ide detect` | [`commands/ide.py:421`](../../aqp_cli/src/aqp_cli/commands/ide.py) | List every reachable Theia (local + cluster). |
| `aqp-cli ide doctor` | [`commands/ide.py:469`](../../aqp_cli/src/aqp_cli/commands/ide.py) | Preflight checks (yarn / port / lockfile / auth / running pid). |
| `_THEIA_ENV_KEYS: tuple[str, ...]` | [`commands/ide.py:336`](../../aqp_cli/src/aqp_cli/commands/ide.py) | The 17-key source of truth for the `AQP_THEIA_*` block. |

### `aqp_cli.config.AqpCliSettings` (IDE-related fields)

| Field | Default | Source |
| --- | --- | --- |
| `theia_port: int` | `3000` | [`config.py:73`](../../aqp_cli/src/aqp_cli/config.py) |
| `theia_url: str` | `http://localhost:3000` | [`config.py:79`](../../aqp_cli/src/aqp_cli/config.py) |
| `theia_workspace: str` | `""` | [`config.py:83`](../../aqp_cli/src/aqp_cli/config.py) |
| `theia_yarn_offline: bool` | `False` | [`config.py:90`](../../aqp_cli/src/aqp_cli/config.py) |
| `theia_docker_image: str` | `aqp/aqp-ide:dev` | [`config.py:94`](../../aqp_cli/src/aqp_cli/config.py) |

## `theia-ide-aqp-ext` (TypeScript) — updated surfaces

| Symbol | Source | Summary |
| --- | --- | --- |
| `AqpMcpConfigSlot` | [`aqp/src/common/aqp-protocol.ts:82`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | Per-MCP-surface config: `{ url, audience }` (AGENTS rule 49). |
| `AqpRuntimeConfig` | [`aqp/src/common/aqp-protocol.ts:87`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | Runtime config served on `GET /aqp/config`; now includes `mcp?` + `copilot?` slots. |
| `AqpConfigEndpoint` | [`aqp/src/node/aqp-config-endpoint.ts:31`](../../aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts) | Theia Node backend that reads `AQP_THEIA_*` (now incl. `AQP_THEIA_MCP_*` + `AQP_THEIA_SERA_*`) and serves them as JSON. |
| `KILL_SWITCH_ENDPOINTS` | [`aqp/src/common/aqp-protocol.ts:45`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | Nine endpoints fanned out by `aqp.haltAll` — mirrors the `aqp_client` KillSwitch. |
| `TenancyHeaders` | [`aqp/src/common/aqp-protocol.ts:62`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | `X-AQP-Workspace` / `X-AQP-Project` / `X-AQP-Lab` / `X-AQP-Org` / `X-AQP-Team`. |
| `AqpCommandIds`, `AqpViewIds` | [`aqp/src/common/aqp-protocol.ts:18`, `:31`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | Command + view id constants. |

## `theia-ide-aqp-shell-ext` (TypeScript)

| Symbol | Source | Summary |
| --- | --- | --- |
| `AqpAboutDialogContribution` (`@injectable`) | [`aqp-shell/src/browser/about/aqp-about-dialog-contribution.ts:39`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/about/aqp-about-dialog-contribution.ts) | Rebinds `Help → About` to the AQP branding block. |
| `AqpWindowTitleContribution` (`@injectable`) | [`aqp-shell/src/browser/window/aqp-window-title-contribution.ts:32`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/window/aqp-window-title-contribution.ts) | Sets window title to `AQP IDE — <tenancy>` once signed in. |
| `AqpFilterContribution` (`@injectable`) | [`aqp-shell/src/browser/filters/aqp-filter-contribution.ts:33`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/filters/aqp-filter-contribution.ts) | Additive include/exclude filters that hide unwanted upstream contributions. |

## `theia-ide-aqp-mcp-bridge-ext` (TypeScript)

| Symbol | Source | Summary |
| --- | --- | --- |
| `AqpMcpCommandIds` | [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts:14`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | Command id constants (`aqp.mcp.reconnect`, `aqp.mcp.status`). |
| `AQP_MCP_SERVER_NAMES` | [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts:25`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | Frozen `{ DATA, CODEBASE }` canonical-name dictionary. |
| `AqpMcpServerConfig` | [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts:40`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | `{ url, audience }` slot consumed from `AqpRuntimeConfig.mcp.*`. |
| `AqpMcpSurface` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts:21`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | `{ name, description, cfgKey }`. |
| `AQP_MCP_SURFACES` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts:27`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | Frozen list of surfaces — single registration loop. |
| `staticHeadersFor(...)` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts:46`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | Builds the `X-AQP-MCP-Audience` + tenancy headers. |
| `describeSurfaceConfig(...)` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts:60`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | Human-readable status string. |
| `MCPServerDescriptionLike` / `MCPServerManagerLike` / `MCPServerManager` (symbol) | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts:33`, `:42`, `:48`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) | Structural typing on the upstream `@theia/ai-mcp` surface (no hard dep). |
| `AqpMcpRegistrationStatus` | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts:50`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) | Per-surface registration status. |
| `AqpMcpRegistrar` (`@injectable`) | [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts:80`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) | `FrontendApplicationContribution` that registers + re-registers MCP servers per-tenancy with per-MCP `aud`. |
| `AqpMcpContribution` (`@injectable`) | [`aqp-mcp-bridge/src/browser/commands/aqp-mcp-contribution.ts:45`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/commands/aqp-mcp-contribution.ts) | Exposes `AQP: MCP — Reconnect All` + `AQP: MCP — Show Status`. |

## `theia-ide-aqp-research-copilot-ext` (TypeScript)

| Symbol | Source | Summary |
| --- | --- | --- |
| `AqpCopilotIds` | [`aqp-research-copilot/src/common/aqp-copilot-protocol.ts:15`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/common/aqp-copilot-protocol.ts) | Agent id + prompt id constants. |
| `RouterCompleteRequest` / `RouterCompleteResponse` | [`aqp-research-copilot/src/common/aqp-copilot-protocol.ts:36`, `:57`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/common/aqp-copilot-protocol.ts) | Wire shapes for the `POST /llm/router/complete` round-trip. |
| `RouterCompleteClient` (`@injectable`) | [`aqp-research-copilot/src/browser/copilot/router-complete-client.ts:32`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/router-complete-client.ts) | The only LLM caller; mints Auth0 bearer, redacts tokens to 4-char prefix. |
| `AqpToolDescriptor` | [`aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts:19`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts) | Tool-function descriptor shape. |
| `AqpToolRegistry` (`@injectable`) | [`aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts:41`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts) | Curated registry wrapping `/agents`, `/workflows`, `/bots`, `/rl`, `/analysis`, `/backtest`. |
| `AqpAgent` | [`aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts:23`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts) | Interface for an AQP-flavoured chat agent. |
| `AqpResearchAgent` (`@injectable`) | [`aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts:51`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts) | Theia AI `ChatAgent` implementation; registers prompts + bridged MCP tools. |

## `theia-ide-aqp-notebook-quant-ext` (TypeScript)

| Symbol | Source | Summary |
| --- | --- | --- |
| `AQP_PERSPECTIVE_ARROW_MIME` | [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts:21`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | `application/vnd.aqp.perspective-arrow+arrow`. |
| `AQP_PERSPECTIVE_ARROW_RENDERER_ID` | [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts:24`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | `aqp-perspective-arrow`. |
| `AqpNotebookCommandIds` | [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts:27`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | Command id constants (`aqp.notebook.new`). |
| `AQP_NOTEBOOK_HELPER_CELL` | [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts:40`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | The pre-populated first cell that imports `aqp.notebook.helpers`. |
| `AqpRendererOutputItem` | [`aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts:24`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts) | Shape of a notebook output item the renderer accepts. |
| `PerspectiveArrowRenderer` (`@injectable`) | [`aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts:61`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts) | Lazy-mounts `<perspective-viewer>` per cell that emits the AQP MIME type. |
| `AqpNotebookScaffolder` (`@injectable`) | [`aqp-notebook-quant/src/browser/notebook/aqp-notebook-scaffolder.ts:27`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/aqp-notebook-scaffolder.ts) | Writes a new `.ipynb` whose first cell imports `aqp.notebook.helpers`. |
| `AqpNotebookContribution` (`@injectable`) | [`aqp-notebook-quant/src/browser/commands/aqp-notebook-contribution.ts:43`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/commands/aqp-notebook-contribution.ts) | `File → New AQP Notebook` command + menu wiring. |

## `theia-ide-aqp-quant-ext` (TypeScript)

| Symbol | Source | Summary |
| --- | --- | --- |
| `AqpQuantViewIds` | [`aqp-quant/src/common/aqp-quant-protocol.ts:29`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | View id constants. |
| `AqpQuantCommandIds` | [`aqp-quant/src/common/aqp-quant-protocol.ts:35`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | Command id constants. |
| `AQP_SPEC_KINDS` | [`aqp-quant/src/common/aqp-quant-protocol.ts:47`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | Frozen list of the five hash-locked spec kinds (Agent / Bot / RL / Analysis / Workflow). |
| `AqpProgressFrame` | [`aqp-quant/src/common/aqp-quant-protocol.ts:115`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | `{ task_id, stage, message, timestamp, ...extras }` — AGENTS rule 4 verbatim. |
| `AqpSpecSummary` | [`aqp-quant/src/common/aqp-quant-protocol.ts:128`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | Summary row returned by spec list endpoints. |
| `AqpRuntimeClient` (`@injectable`) | [`aqp-quant/src/browser/services/aqp-runtime-client.ts:28`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-runtime-client.ts) | REST wrapper for spec + run endpoints across the five runtimes. |
| `AqpTaskSubscription` | [`aqp-quant/src/browser/services/aqp-ws-client.ts:23`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-ws-client.ts) | Disposable subscription returned by `AqpWsClient.subscribe`. |
| `AqpWsClient` (`@injectable`) | [`aqp-quant/src/browser/services/aqp-ws-client.ts:44`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-ws-client.ts) | WebSocket client honouring `AqpProgressFrame` (AGENTS rule 4). |
| `SpecAuthorWidget` (`@injectable`) | [`aqp-quant/src/browser/widgets/spec-author-widget.tsx:37`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/spec-author-widget.tsx) | JSON-schema-driven editor for the five hash-locked specs. |
| `RunInspectorWidget` (`@injectable`) | [`aqp-quant/src/browser/widgets/run-inspector-widget.tsx:30`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/run-inspector-widget.tsx) | Live-tail any `*_runs` ledger row over WebSocket. |
| `BacktestRunnerWidget` (`@injectable`) | [`aqp-quant/src/browser/widgets/backtest-runner-widget.tsx:35`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/backtest-runner-widget.tsx) | Single dispatch widget for the five-runtime backtest surface. |
| `SpecAuthorViewContribution` (`@injectable`) | [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts:55`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | `View → AQP → Author Spec` view + menu. |
| `RunInspectorViewContribution` (`@injectable`) | [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts:79`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | `View → AQP → Inspect Run` view + menu. |
| `BacktestRunnerViewContribution` (`@injectable`) | [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts:116`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | `View → AQP → Run Backtest` view + menu. |
