---
title: 'Repository orientation'
summary: 'Top-level map of every aqp_* package and where each subsystem lives in the monorepo.'
owner: docs-team
last_reviewed: 2026-05-25
audience: both
sidebar_position: 4
---

# Repository orientation

AQP is a monorepo organised by responsibility. The boundary between
packages is enforced by the always-on Cursor rule
[repository-boundaries.mdc](https://github.com/julianwileymac/agentic_quant_platform/blob/main/.cursor/rules/repository-boundaries.mdc)
and by `import` guards in CI.

## Top-level packages

- **`aqp/`** — the quant runtime. FastAPI gateway, Celery workers,
  strategy framework, backtest engines, agent control plane, RAG,
  Iceberg writers, persistence models.
- **`aqp_control_plane/`** — workload lifecycle / `/manage/*` API /
  Terraform driver / provider adapters. Never imports `aqp.*`. See
  [Concept: control plane topology](../concepts/infrastructure/control-plane-topology.md).
- **`aqp_platform_core/`** — shared value types, ABCs, auth filters,
  topology contracts. Dependency-light.
- **`aqp_client/`** — active Vite + React 19 + Tailwind 4 operator UI.
  Served at `aqp.fund`.
- **`aqp_ui/`** — cloud-hosted, customer-facing PaaS frontend
  (Next.js 14+). Served at `aqp.fund`. Dual Auth0 (B2C) + Entra (B2B)
  identity.
- **`aqp_admin/`** — internal admin (managed services + company
  accounts). Audit-first. Served at `manage.aqp.fund`.
- **`aqp_rl/`** — RL subsystem: hash-locked `RLExperimentSpec` +
  `RLRuntime` + Iceberg trajectory store. Legacy `aqp.rl.*` is a
  deprecation shim.
- **`aqp_models/`** — custom model pulling, building, training,
  evaluating, serving (vLLM + Ollama). Legacy `aqp.ml.*` is a
  deprecation shim.
- **`aqp_bots/`** — bot templates and bot runtime
  (`TradingBot` / `ResearchBot`).
- **`aqp_ide/`** — Theia 1.72-based IDE + AQP extensions
  (`aqp`, `aqp-shell`, `aqp-mcp-bridge`, `aqp-research-copilot`,
  `aqp-notebook-quant`, `aqp-quant`).
- **`aqp_cli/`** — standalone operator CLI (`aqp-cli`). HTTP-only;
  never imports `aqp.*`. RFC 8628 device auth + OS keyring storage.
- **`aqp_platform/`** — hosted deployment + build + IaC + cluster
  setup. Manifests, Helm charts, Terraform modules, Docker base
  images. No Python runtime imports.
- **`aqp_index/`** — single source of truth for project orientation
  (this site links into it but never modifies it; sole-writer is the
  `aqp-index-curator` subagent).
- **`aqp_docs/`** — this site.

## Where to look for X

- API route: [`aqp/api/routes/`](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp/api/routes).
- Celery task: [`aqp/tasks/`](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp/tasks).
- Strategy: [`aqp/strategies/`](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp/strategies).
- Persistence model: [`aqp/persistence/`](https://github.com/julianwileymac/agentic_quant_platform/tree/main/aqp/persistence).
- Migration: [`alembic/versions/`](https://github.com/julianwileymac/agentic_quant_platform/tree/main/alembic/versions).
- Iceberg writer: [`aqp/data/iceberg_catalog.py`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/data/iceberg_catalog.py).
- LLM gateway: [`aqp/llm/providers/router.py`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/llm/providers/router.py).
- Configuration: [`aqp/config/settings.py`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp/config/settings.py).

## Hard rules

The full agent-readable rule-set is in
[AGENTS.md](https://github.com/julianwileymac/agentic_quant_platform/blob/main/AGENTS.md).
The cardinal subset:

1. **Symbols**: `Symbol.parse(vt_symbol)` — never split on `.`.
2. **LLM calls**: `router_complete` only — never `litellm.completion`
   or vendor SDKs.
3. **Iceberg writes**: `iceberg_catalog.append_arrow` only — never
   raw PyIceberg.
4. **Celery progress**: `emit / emit_done / emit_error` from
   `aqp/tasks/_progress.py` — never publish to Redis from task code.
5. **Configuration**: `from aqp.config import settings` — never
   construct a fresh `Settings()`.
6. **Registry**: `@register("Name", kind=...)` for every new
   strategy / model / engine / alpha / portfolio / sink.
7. **Migrations**: immutable once committed.
8. **Cross-task state**: Postgres only; never pickle ORM objects.

The full set is 55 hard rules + a Don'ts section in AGENTS.md.

## Conventions

See [Conventions](./conventions.md) for documentation style and
authoring rules.
