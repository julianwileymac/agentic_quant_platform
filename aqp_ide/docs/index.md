# theia-ide documentation index

Canonical documentation map for this workspace.

## Status taxonomy

- `active` — current and maintained documentation.
- `migration` — transition guidance for AQP-specific integration.
- `rollback` — retained for compatibility/reference only.
- `archive` — historical snapshots and one-off notes.

## Core docs

| Doc | Status | Purpose |
| --- | --- | --- |
| [../README.md](../README.md) | active | Repository onboarding and build workflow |
| [../AGENTS.md](../AGENTS.md) | active | Agent-facing guardrails |
| [aqp-monorepo-paths.md](aqp-monorepo-paths.md) | active | AQP path contract |
| [code-index.md](code-index.md) | active | Agent-readable ownership map |
| [mcp-integration.md](mcp-integration.md) | migration | AQP MCP integration guidance |
| [../theia-extensions/aqp/README.md](../theia-extensions/aqp/README.md) | migration | AQP extension integration runbook |
| [../theia-extensions/aqp/AGENTS.md](../theia-extensions/aqp/AGENTS.md) | active | Scoped AQP extension agent contract |
| [archive/README.md](archive/README.md) | archive | Retention policy for historical notes |

## Governance docs

| Doc | Status | Purpose |
| --- | --- | --- |
| [../.cursor/agents/aqp-theia-integration.md](../.cursor/agents/aqp-theia-integration.md) | active | AQP Theia integration guardrails |
| [../.cursor/rules/theia-aqp-integration.mdc](../.cursor/rules/theia-aqp-integration.mdc) | active | Rule boundary for AQP integration surfaces |
| [../.cursor/rules/theia-mcp-integration.mdc](../.cursor/rules/theia-mcp-integration.mdc) | active | MCP/code-index integration rule |
| [../.cursor/skills/aqp-theia-mcp/SKILL.md](../.cursor/skills/aqp-theia-mcp/SKILL.md) | active | Repeatable MCP integration workflow |

## Operational snippet catalog

```bash
yarn
yarn build:extensions
yarn build:applications:dev
yarn browser start
```
