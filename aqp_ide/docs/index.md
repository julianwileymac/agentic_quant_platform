# AQP IDE documentation index

Canonical documentation map for this workspace.

## Status taxonomy

- `active` — current and maintained documentation.
- `migration` — transition guidance for AQP-specific integration.
- `rollback` — retained for compatibility/reference only.
- `archive` — historical snapshots and one-off notes.

## Core docs

| Doc | Status | Purpose |
| --- | --- | --- |
| [../README.md](../README.md) | active | Workspace overview, build commands, extension list |
| [../AGENTS.md](../AGENTS.md) | active | Agent-facing guardrails |
| [architecture.md](architecture.md) | active | Process diagram + the four extension mechanisms + JSON-RPC + MCP |
| [extensions.md](extensions.md) | active | Per-extension reference for all six AQP extensions |
| [cli-entrypoint.md](cli-entrypoint.md) | active | Full `aqp-cli ide` cookbook (canonical operator entrypoint) |
| [mcp-integration.md](mcp-integration.md) | active | DataMCP + CodebaseMCP wiring details (AQP rule 49) |
| [research-copilot.md](research-copilot.md) | active | Theia AI chat agent + prompts + tools + `router_complete` |
| [notebook.md](notebook.md) | active | Perspective Arrow MIME renderer + `aqp.notebook.helpers` |
| [quant-widgets.md](quant-widgets.md) | active | SpecAuthor / RunInspector / BacktestRunner reference |
| [deployment.md](deployment.md) | active | Docker + single-pod K8s + Theia Cloud roadmap |
| [retire-vendored-workspace.md](retire-vendored-workspace.md) | migration | Checklist for deleting `test_theia/theia-ide` |
| [aqp-monorepo-paths.md](aqp-monorepo-paths.md) | active | AQP path contract |
| [code-index.md](code-index.md) | active | Agent-readable ownership map |
| [archive/README.md](archive/README.md) | archive | Retention policy for historical notes |

## Per-extension reference

| Extension | README | AGENTS |
| --- | --- | --- |
| `theia-extensions/aqp` | [README.md](../theia-extensions/aqp/README.md) | [AGENTS.md](../theia-extensions/aqp/AGENTS.md) |
| `theia-extensions/aqp-shell` | [README.md](../theia-extensions/aqp-shell/README.md) | [AGENTS.md](../theia-extensions/aqp-shell/AGENTS.md) |
| `theia-extensions/aqp-mcp-bridge` | [README.md](../theia-extensions/aqp-mcp-bridge/README.md) | [AGENTS.md](../theia-extensions/aqp-mcp-bridge/AGENTS.md) |
| `theia-extensions/aqp-research-copilot` | [README.md](../theia-extensions/aqp-research-copilot/README.md) | [AGENTS.md](../theia-extensions/aqp-research-copilot/AGENTS.md) |
| `theia-extensions/aqp-notebook-quant` | [README.md](../theia-extensions/aqp-notebook-quant/README.md) | [AGENTS.md](../theia-extensions/aqp-notebook-quant/AGENTS.md) |
| `theia-extensions/aqp-quant` | [README.md](../theia-extensions/aqp-quant/README.md) | [AGENTS.md](../theia-extensions/aqp-quant/AGENTS.md) |

## Monorepo-wide references

| Doc | Purpose |
| --- | --- |
| [../../aqp_docs/aqp-ide.md](../../aqp_docs/aqp-ide.md) | SSoT pointer from AQP docs side |
| [../../aqp_docs/aqp-ide-roadmap.md](../../aqp_docs/aqp-ide-roadmap.md) | Blueprint → AQP phasing |
| [../../aqp_docs/data-mcp.md](../../aqp_docs/data-mcp.md) | AQP DataMCP boundary (rule 22) |
| [../../aqp_docs/codebase-mcp.md](../../aqp_docs/codebase-mcp.md) | AQP Codebase MCP (rule 22) |
| [../../aqp_docs/providers.md](../../aqp_docs/providers.md) | `router_complete` LLM gateway (rule 2) |
| [../../aqp_docs/identity.md](../../aqp_docs/identity.md) | Auth0 / IdentityProvider (rule 27) |
| [../../aqp_docs/management-engine.md](../../aqp_docs/management-engine.md) | WorkloadRuntime (rule 45) |

## Governance docs

| Doc | Status | Purpose |
| --- | --- | --- |
| [../.cursor/agents/aqp-theia-integration.md](../.cursor/agents/aqp-theia-integration.md) | active | AQP Theia integration subagent |
| [../.cursor/agents/aqp-ide-curator.md](../.cursor/agents/aqp-ide-curator.md) | active | IDE docs curator subagent |
| [../.cursor/rules/theia-aqp-integration.mdc](../.cursor/rules/theia-aqp-integration.mdc) | active | Rule boundary for AQP integration surfaces |
| [../.cursor/rules/aqp-ide-mcp.mdc](../.cursor/rules/aqp-ide-mcp.mdc) | active | MCP integration rule (RFC 9728 + RFC 8707) |
| [../.cursor/skills/aqp-theia-mcp/SKILL.md](../.cursor/skills/aqp-theia-mcp/SKILL.md) | active | Repeatable MCP integration workflow |
| [../.cursor/skills/aqp-quant-widget/SKILL.md](../.cursor/skills/aqp-quant-widget/SKILL.md) | active | Step-by-step skill for adding a quant widget |
| [../.cursor/skills/aqp-mcp-wiring/SKILL.md](../.cursor/skills/aqp-mcp-wiring/SKILL.md) | active | Step-by-step skill for adding a new MCP server |

## Operational snippet catalog

The canonical operator entrypoint is `aqp-cli ide`:

```bash
aqp-cli auth login --device
aqp-cli ide install
aqp-cli ide build --dev
aqp-cli ide start --open
```

Native Theia (inner-loop dev):

```bash
yarn install
yarn build:extensions
yarn build:applications:dev
yarn browser start
```
