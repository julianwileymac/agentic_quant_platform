# Module map

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — first signature-populated section covers the six new
> Theia extensions, the updated AQP extension config endpoint, and
> `aqp/notebook/`).
>
> This file is curator-generated. See [index.md](index.md) for the
> methodology. Humans must not edit this file by hand.

## Coverage targets

The curator MUST populate one section per top-level package:

- `aqp/` (full tree, depth-first) — **partial**: `aqp/notebook/` only (added with the AQP IDE work)
- `aqp_client/src/` — *pending*
- `aqp_control_plane/src/aqp_cp/` — *pending*
- `aqp_platform_core/src/aqp_platform_core/` — *pending*
- `aqp_bots/` — *pending*
- `aqp_rl/src/aqp_rl/` — *pending*
- `aqp_models/src/aqp_models/` — *pending*
- `aqp_cli/src/aqp_cli/` — **partial**: `aqp_cli/src/aqp_cli/commands/ide.py` + `config.py` only (added with the AQP IDE work)
- `aqp_admin/src/aqp_admin/` — *pending*
- `aqp_ide/theia-extensions/aqp*/` — **populated** (the six AQP extensions)

Each section is a table of `(module, range, signature, one-line summary)`
rows. *pending* areas: read source directly OR file a `.cursor/plans/`
note asking the curator to populate the matching section.

---

## `aqp/notebook/`

Tenancy-aware helpers consumed by the AQP IDE's notebook scaffolder cell.

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp/notebook/__init__.py`](../../aqp/notebook/__init__.py) | 1-15 | `from .helpers import AqpNotebookContext, attach` | Single public surface: `attach()` + `AqpNotebookContext`. |
| [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) | 41-175 | `@dataclasses.dataclass class AqpNotebookContext` | Composite handle for a tenancy-scoped notebook session (`ctx.data`, `ctx.codebase`, `ctx.router`, `ctx.perspective(table)`, `ctx.tenancy_summary()`). |
| [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) | 178-197 | `class _UnavailableHelper` | Stand-in returned when an AQP submodule cannot be imported (surfaces a clear error at call time). |
| [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) | 200-226 | `class _RouterCompleteFacade` | Tiny ergonomic wrapper around `router_complete` so notebooks can `ctx.router.complete(prompt='...')`. |
| [`aqp/notebook/helpers.py`](../../aqp/notebook/helpers.py) | 229-257 | `def attach(*, org=None, team=None, workspace=None, project=None, lab=None) -> AqpNotebookContext` | Build an `AqpNotebookContext`; each kwarg defaults to its matching `AQP_*` env var when omitted. |

## `aqp_cli/src/aqp_cli/commands/ide.py` + `config.py`

The canonical operator entrypoint for the AQP IDE.

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 54 | `app = typer.Typer(no_args_is_help=True, help="Control the AQP Theia IDE.")` | Top-level Typer app for the `aqp-cli ide` command group. |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 128-144 | `install(frozen: bool = ...)` | `yarn install` inside `aqp_ide/` (one-time bootstrap). |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 147-162 | `build(dev: bool = ...)` | `yarn build:extensions` then `build:applications[:dev]`. |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 170-251 | `start(background, port, workspace, open_browser)` | Spawn Theia (foreground or background); persists `pid` / `port` / `url` to the state file. |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 254-282 | `stop()` / `status()` / `logs(lines)` | Process-manager primitives for the backgrounded Theia. |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 290-328 | `open_browser(no_browser)` + `url(remote)` | Open or print the IDE URL (local from state file OR `--remote` from cluster topology). |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 336-354 | `_THEIA_ENV_KEYS: tuple[str, ...]` | Source of truth for the `AQP_THEIA_*` env var list (17 keys). |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 357-418 | `env(write)` | Resolve `AQP_THEIA_*` from env + control-plane topology; print or write to a file. |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 421-466 | `detect()` | Surface every reachable Theia instance (local pid + cluster topology). |
| [`aqp_cli/src/aqp_cli/commands/ide.py`](../../aqp_cli/src/aqp_cli/commands/ide.py) | 469-530 | `doctor()` | Preflight checks (yarn, port, lockfile, auth token, running pid). |
| [`aqp_cli/src/aqp_cli/config.py`](../../aqp_cli/src/aqp_cli/config.py) | 73-97 | `AqpCliSettings.theia_port / theia_url / theia_workspace / theia_yarn_offline / theia_docker_image` | Five `AQP_CLI_THEIA_*` settings consumed by the `ide` command group. |
| [`aqp_cli/src/aqp_cli/config.py`](../../aqp_cli/src/aqp_cli/config.py) | 51-62 | `ide_state_file / ide_log_file` settings + `ide_state_path()` / `ide_log_path()` helpers | State + log file paths for the background Theia process. |

## `aqp_ide/theia-extensions/aqp/` (existing extension — config endpoint + runtime config extended)

The pre-existing AQP extension; this pass refreshes only the changed
surfaces (`src/common/aqp-protocol.ts` and `src/node/aqp-config-endpoint.ts`).

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 16 | `export const AQP_EXTENSION_ID = 'theia-aqp-ext'` | Stable extension id (constant). |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 18-29 | `export namespace AqpCommandIds` | Command id constants (login / logout / haltAll / openAgents / openWorkflows / openBots / openTopology / openManagement / setTenancy). |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 31-38 | `export namespace AqpViewIds` | View id constants (agentRuns / workflows / bots / topology / management). |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 45-56 | `export const KILL_SWITCH_ENDPOINTS: readonly string[]` | Nine endpoints fanned out by the `aqp.haltAll` command (mirrors the `aqp_client` KillSwitch). |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 62-68 | `export namespace TenancyHeaders` | `X-AQP-Workspace` / `X-AQP-Project` / `X-AQP-Lab` / `X-AQP-Org` / `X-AQP-Team` header names. |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 82-85 | `export interface AqpMcpConfigSlot` | Per-MCP-surface config: `{ url, audience }` (AGENTS rule 49). |
| [`theia-extensions/aqp/src/common/aqp-protocol.ts`](../../aqp_ide/theia-extensions/aqp/src/common/aqp-protocol.ts) | 87-125 | `export interface AqpRuntimeConfig` | Runtime config served on `GET /aqp/config`. Now includes `mcp?: { data?, codebase? }` and `copilot?: { seraEnabled?, routerCompletePath? }` slots. |
| [`theia-extensions/aqp/src/node/aqp-config-endpoint.ts`](../../aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts) | 30-92 | `@injectable() class AqpConfigEndpoint implements BackendApplicationContribution` | Theia Node backend that reads `AQP_THEIA_*` env vars (including the new `AQP_THEIA_MCP_*` and `AQP_THEIA_SERA_*` slots) and serves them as JSON on `GET /aqp/config`. `Cache-Control: no-store`. |

## `aqp_ide/theia-extensions/aqp-shell/` (NEW)

White-label theme + filters + window title + about dialog.

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp-shell/src/browser/aqp-shell-frontend-module.ts`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/aqp-shell-frontend-module.ts) | – | `export default new ContainerModule(...)` | Frontend DI module entrypoint declared by `theiaExtensions` in [`package.json`](../../aqp_ide/theia-extensions/aqp-shell/package.json). |
| [`aqp-shell/src/browser/about/aqp-about-dialog-contribution.ts`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/about/aqp-about-dialog-contribution.ts) | 38-39 | `@injectable() class AqpAboutDialogContribution implements CommandContribution, MenuContribution` | Rebinds `Help → About` to the AQP branding block. |
| [`aqp-shell/src/browser/window/aqp-window-title-contribution.ts`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/window/aqp-window-title-contribution.ts) | 31-32 | `@injectable() class AqpWindowTitleContribution implements FrontendApplicationContribution` | Sets the window title to `AQP IDE — <tenancy>` once signed in. |
| [`aqp-shell/src/browser/filters/aqp-filter-contribution.ts`](../../aqp_ide/theia-extensions/aqp-shell/src/browser/filters/aqp-filter-contribution.ts) | 32-33 | `@injectable() class AqpFilterContribution implements FilterContribution` | Additive `include` / `exclude` patterns that hide upstream Theia contributions (Getting Started walkthrough, Git Welcome, ...). |

## `aqp_ide/theia-extensions/aqp-mcp-bridge/` (NEW)

The sole sanctioned consumer of `MCPServerManager.addOrUpdateServer(...)` inside `aqp_ide/` (AGENTS rules 22, 49).

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp-mcp-bridge/src/browser/aqp-mcp-bridge-frontend-module.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/aqp-mcp-bridge-frontend-module.ts) | – | `export default new ContainerModule(...)` | Frontend DI module entrypoint. |
| [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | 14 | `export namespace AqpMcpCommandIds` | Command id constants (e.g. `aqp.mcp.reconnect`, `aqp.mcp.status`). |
| [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | 25-31 | `export const AQP_MCP_SERVER_NAMES = Object.freeze({ DATA, CODEBASE })` | Canonical names — the cross-extension wire contract. |
| [`aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/common/aqp-mcp-protocol.ts) | 40 | `export interface AqpMcpServerConfig` | `{ url, audience }` slot consumed from `AqpRuntimeConfig.mcp.*`. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | 21 | `export interface AqpMcpSurface` | Surface descriptor — `{ name, description, cfgKey }`. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | 27 | `export const AQP_MCP_SURFACES: readonly AqpMcpSurface[]` | Frozen list of surfaces; `AqpMcpRegistrar.reregisterAll()` iterates over it. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | 46 | `export function staticHeadersFor(...)` | Builds the non-secret `X-AQP-MCP-Audience` + tenancy header set. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-server-spec.ts) | 60 | `export function describeSurfaceConfig(...)` | Human-readable status for `AQP: MCP — Show Status`. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) | 33-50 | `export interface MCPServerDescriptionLike` / `MCPServerManagerLike` / `AqpMcpRegistrationStatus` | Structural types describing the upstream `@theia/ai-mcp` surface. |
| [`aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/mcp/aqp-mcp-registrar.ts) | 79-80 | `@injectable() class AqpMcpRegistrar implements FrontendApplicationContribution` | Registrar: mints per-MCP `aud` tokens via `Auth0Service` + re-registers on every tenancy change. |
| [`aqp-mcp-bridge/src/browser/commands/aqp-mcp-contribution.ts`](../../aqp_ide/theia-extensions/aqp-mcp-bridge/src/browser/commands/aqp-mcp-contribution.ts) | 44-45 | `@injectable() class AqpMcpContribution implements CommandContribution, MenuContribution` | Exposes `AQP: MCP — Reconnect All` and `AQP: MCP — Show Status` commands. |

## `aqp_ide/theia-extensions/aqp-research-copilot/` (NEW)

Theia AI `ChatAgent` routed through AQP's `router_complete` LLM gateway (AGENTS rule 2).

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp-research-copilot/src/browser/aqp-research-copilot-frontend-module.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/aqp-research-copilot-frontend-module.ts) | – | `export default new ContainerModule(...)` | Frontend DI module entrypoint. |
| [`aqp-research-copilot/src/common/aqp-copilot-protocol.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/common/aqp-copilot-protocol.ts) | 15 | `export namespace AqpCopilotIds` | Command id + prompt id constants. |
| [`aqp-research-copilot/src/common/aqp-copilot-protocol.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/common/aqp-copilot-protocol.ts) | 36 | `export interface RouterCompleteRequest` | Wire shape of a `POST /llm/router/complete` request. |
| [`aqp-research-copilot/src/common/aqp-copilot-protocol.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/common/aqp-copilot-protocol.ts) | 57 | `export interface RouterCompleteResponse` | Wire shape of the response. |
| [`aqp-research-copilot/src/browser/copilot/router-complete-client.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/router-complete-client.ts) | 31-32 | `@injectable() class RouterCompleteClient` | The only sanctioned LLM caller in the IDE; mints Auth0 bearer, redacts to 4-char prefix on log. |
| [`aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts) | 19 | `export interface AqpToolDescriptor` | Tool-function descriptor shape for the chat agent. |
| [`aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-tool-functions.ts) | 40-41 | `@injectable() class AqpToolRegistry` | Curated tool-function registry wrapping `/agents`, `/workflows`, `/bots`, `/rl`, `/analysis`, `/backtest`. |
| [`aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts) | 23 | `export interface AqpAgent` | Public interface for an AQP-flavoured chat agent. |
| [`aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/aqp-research-agent.ts) | 50-51 | `@injectable() class AqpResearchAgent implements AqpAgent` | Theia AI `ChatAgent` implementation; registers prompts and bridged MCP tools. |
| [`aqp-research-copilot/src/browser/copilot/prompts/codebase-navigation.md`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/prompts/codebase-navigation.md) | – | (prompt fragment) | `/codebase-navigation` prompt fragment registered with the chat agent. |
| [`aqp-research-copilot/src/browser/copilot/prompts/factor-research.md`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/prompts/factor-research.md) | – | (prompt fragment) | `/factor-research` prompt fragment. |
| [`aqp-research-copilot/src/browser/copilot/prompts/spec-authoring.md`](../../aqp_ide/theia-extensions/aqp-research-copilot/src/browser/copilot/prompts/spec-authoring.md) | – | (prompt fragment) | `/spec-authoring` prompt fragment. |

## `aqp_ide/theia-extensions/aqp-notebook-quant/` (NEW)

FINOS Perspective MIME renderer for Arrow + `File → New AQP Notebook` scaffolder.

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp-notebook-quant/src/browser/aqp-notebook-quant-frontend-module.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/aqp-notebook-quant-frontend-module.ts) | – | `export default new ContainerModule(...)` | Frontend DI module entrypoint. |
| [`aqp-notebook-quant/src/node/aqp-notebook-quant-backend-module.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/node/aqp-notebook-quant-backend-module.ts) | – | `export default new ContainerModule(...)` | Backend DI module (notebook scaffold writes go through Theia's filesystem service from Node, not browser). |
| [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | 21 | `export const AQP_PERSPECTIVE_ARROW_MIME = 'application/vnd.aqp.perspective-arrow+arrow'` | Custom MIME type for the renderer. |
| [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | 24 | `export const AQP_PERSPECTIVE_ARROW_RENDERER_ID = 'aqp-perspective-arrow'` | Renderer id registered with Theia notebook. |
| [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | 27 | `export namespace AqpNotebookCommandIds` | Command id constants (`aqp.notebook.new`). |
| [`aqp-notebook-quant/src/common/aqp-notebook-protocol.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/common/aqp-notebook-protocol.ts) | 40 | `export const AQP_NOTEBOOK_HELPER_CELL: readonly string[]` | Lines of the pre-populated first cell that imports `aqp.notebook.helpers`. |
| [`aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts) | 24 | `export interface AqpRendererOutputItem` | Shape of a notebook output item the renderer accepts. |
| [`aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/perspective-mime-renderer.ts) | 60-61 | `@injectable() class PerspectiveArrowRenderer implements FrontendApplicationContribution` | Lazy-mounts a `<perspective-viewer>` for each cell that emits the AQP MIME type. |
| [`aqp-notebook-quant/src/browser/notebook/aqp-notebook-scaffolder.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/notebook/aqp-notebook-scaffolder.ts) | 26-27 | `@injectable() class AqpNotebookScaffolder` | Writes a new `.ipynb` whose first cell imports `aqp.notebook.helpers.attach`. |
| [`aqp-notebook-quant/src/browser/commands/aqp-notebook-contribution.ts`](../../aqp_ide/theia-extensions/aqp-notebook-quant/src/browser/commands/aqp-notebook-contribution.ts) | 42-43 | `@injectable() class AqpNotebookContribution implements CommandContribution, MenuContribution` | `File → New AQP Notebook` command + menu wiring. |

## `aqp_ide/theia-extensions/aqp-quant/` (NEW)

Spec authoring + run inspection + backtest dispatch widgets.

| Module | Range | Signature | One-line summary |
| --- | --- | --- | --- |
| [`aqp-quant/src/browser/aqp-quant-frontend-module.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/aqp-quant-frontend-module.ts) | – | `export default new ContainerModule(...)` | Frontend DI module entrypoint. |
| [`aqp-quant/src/common/aqp-quant-protocol.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | 29 | `export namespace AqpQuantViewIds` | View id constants (SPEC_AUTHOR, RUN_INSPECTOR, BACKTEST_RUNNER). |
| [`aqp-quant/src/common/aqp-quant-protocol.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | 35 | `export namespace AqpQuantCommandIds` | Command id constants. |
| [`aqp-quant/src/common/aqp-quant-protocol.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | 47 | `export const AQP_SPEC_KINDS = Object.freeze([...])` | The five hash-locked spec kinds: Agent / Bot / RL / Analysis / Workflow. |
| [`aqp-quant/src/common/aqp-quant-protocol.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | 115 | `export interface AqpProgressFrame` | `{ task_id, stage, message, timestamp, ...extras }` — AGENTS rule 4. |
| [`aqp-quant/src/common/aqp-quant-protocol.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/common/aqp-quant-protocol.ts) | 128 | `export interface AqpSpecSummary` | Summary row returned by spec list endpoints. |
| [`aqp-quant/src/browser/services/aqp-runtime-client.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-runtime-client.ts) | 27-28 | `@injectable() class AqpRuntimeClient` | REST wrapper for `/agents`, `/workflows`, `/bots`, `/rl`, `/analysis`, `/backtest` spec + run endpoints. |
| [`aqp-quant/src/browser/services/aqp-ws-client.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-ws-client.ts) | 23 | `export interface AqpTaskSubscription extends Disposable` | Returned by `AqpWsClient.subscribe(taskId)`. |
| [`aqp-quant/src/browser/services/aqp-ws-client.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/services/aqp-ws-client.ts) | 43-44 | `@injectable() class AqpWsClient` | WebSocket client that honours the canonical `AqpProgressFrame` shape. |
| [`aqp-quant/src/browser/widgets/spec-author-widget.tsx`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/spec-author-widget.tsx) | 36-37 | `@injectable() class SpecAuthorWidget extends AqpWidgetBase` | JSON-schema-driven editor for the five hash-locked specs; saves create a new `*_spec_versions` row. |
| [`aqp-quant/src/browser/widgets/run-inspector-widget.tsx`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/run-inspector-widget.tsx) | 29-30 | `@injectable() class RunInspectorWidget extends AqpWidgetBase` | Live-tail any `*_runs` ledger row over WebSocket (AGENTS rule 4). |
| [`aqp-quant/src/browser/widgets/backtest-runner-widget.tsx`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/widgets/backtest-runner-widget.tsx) | 34-35 | `@injectable() class BacktestRunnerWidget extends AqpWidgetBase` | Single launcher that dispatches to `/bots/{ref}/backtest`, `/workflows/{name}/run`, `/rl/runs`, `/analysis/runs`, or `/backtest/*`. |
| [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | 54-55 | `@injectable() class SpecAuthorViewContribution extends AbstractViewContribution<SpecAuthorWidget>` | View + menu wiring for `View → AQP → Author Spec`. |
| [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | 78-79 | `@injectable() class RunInspectorViewContribution extends AbstractViewContribution<RunInspectorWidget>` | View + menu wiring for `View → AQP → Inspect Run`. |
| [`aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts`](../../aqp_ide/theia-extensions/aqp-quant/src/browser/commands/aqp-quant-view-contributions.ts) | 115-116 | `@injectable() class BacktestRunnerViewContribution extends AbstractViewContribution<BacktestRunnerWidget>` | View + menu wiring for `View → AQP → Run Backtest`. |
