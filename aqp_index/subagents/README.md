# Subagent registry

> Last refreshed: 2026-05-23 (seed).

## What lives here

One file per project subagent. Each file is a *user-facing* description
of the subagent: when to invoke it, what it owns, what it never touches,
and how to extend it.

The subagent **definitions** themselves live at
[../../.cursor/agents/](../../.cursor/agents/). This folder is the index
on top of those definitions, scoped to the curator's view of the project.

## Registry

The registry is rebuilt on each curator pass.

| Subagent | Owner | Scope | Cursor file |
| --- | --- | --- | --- |
| [aqp-index-curator](aqp-index-curator.md) | platform | `aqp_index/**` | [../../.cursor/agents/aqp-index-curator.md](../../.cursor/agents/aqp-index-curator.md) |
| aqp-management-engine | platform | `/manage/*` direct control | [../../.cursor/agents/aqp-management-engine.md](../../.cursor/agents/aqp-management-engine.md) |
| aqp-hard-rules-reviewer | platform | rule 1-47 compliance reviews | [../../.cursor/agents/aqp-hard-rules-reviewer.md](../../.cursor/agents/aqp-hard-rules-reviewer.md) |
| aqp-rules-reviewer | platform | reviewing rule changes | [../../.cursor/agents/aqp-rules-reviewer.md](../../.cursor/agents/aqp-rules-reviewer.md) |
| aqp-run-monitor | platform | implementer fan-out monitor | [../../.cursor/agents/aqp-run-monitor.md](../../.cursor/agents/aqp-run-monitor.md) |
| aqp-agentic-stack-expert | runtime | agent stack (`aqp/agents/`, `aqp/data/mcp/`, `aqp/rag/`) | [../../.cursor/agents/aqp-agentic-stack-expert.md](../../.cursor/agents/aqp-agentic-stack-expert.md) |
| aqp-rl-runtime-expert | rl | RL stack (`aqp/rl/`) | [../../.cursor/agents/aqp-rl-runtime-expert.md](../../.cursor/agents/aqp-rl-runtime-expert.md) |
| aqp-backtest-engine-expert | strategy | backtest engines (`aqp/backtest/`) | [../../.cursor/agents/aqp-backtest-engine-expert.md](../../.cursor/agents/aqp-backtest-engine-expert.md) |
| aqp-frontend-vite-expert | client | `aqp_client/` | [../../.cursor/agents/aqp-frontend-vite-expert.md](../../.cursor/agents/aqp-frontend-vite-expert.md) |
| aqp-kill-switch-expert | client | kill-switch fan-out | [../../.cursor/agents/aqp-kill-switch-expert.md](../../.cursor/agents/aqp-kill-switch-expert.md) |
| aqp-kubernetes-deployment-auditor | platform | deployment topology | [../../.cursor/agents/aqp-kubernetes-deployment-auditor.md](../../.cursor/agents/aqp-kubernetes-deployment-auditor.md) |
| aqp-watchdog-implementer | runtime | agent watchdog | [../../.cursor/agents/aqp-watchdog-implementer.md](../../.cursor/agents/aqp-watchdog-implementer.md) |
| aqp-k8s-docker-implementer | platform | KubernetesAdapter / Docker SDK | [../../.cursor/agents/aqp-k8s-docker-implementer.md](../../.cursor/agents/aqp-k8s-docker-implementer.md) |
| aqp-codebase-mcp-implementer | runtime | `aqp/codebase/mcp/` | [../../.cursor/agents/aqp-codebase-mcp-implementer.md](../../.cursor/agents/aqp-codebase-mcp-implementer.md) |
| aqp-pgvector-implementer | runtime | pgvector control plane | [../../.cursor/agents/aqp-pgvector-implementer.md](../../.cursor/agents/aqp-pgvector-implementer.md) |
| aqp-vite-analytics-implementer | client | analytics frontend routes | [../../.cursor/agents/aqp-vite-analytics-implementer.md](../../.cursor/agents/aqp-vite-analytics-implementer.md) |

## Conventions

- One subagent per file, named `<slug>.md` matching `.cursor/agents/<slug>.md`.
- The user-facing description here MUST be a strict superset of the
  Cursor frontmatter `description` field - so an operator can read this
  page without opening `.cursor/agents/`.
- See [extension.md](extension.md) for how to add a new subagent.
