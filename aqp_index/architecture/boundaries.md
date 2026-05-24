# Repository boundaries

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — refreshed `aqp_ide/` row description to reflect six
> compile-time extensions + `aqp-cli ide` entrypoint).

## Canonical sources

- [../../aqp_docs/repository-split.md](../../aqp_docs/repository-split.md)
  - The full repository-split map.
- [../../aqp_docs/aqp-monorepo-paths.md](../../aqp_docs/aqp-monorepo-paths.md)
  - Canonical paths mirrored by sibling repos.
- [../../AGENTS.md](../../AGENTS.md) section "Repository split routing".
- [../../.cursor/rules/repository-boundaries.mdc](../../.cursor/rules/repository-boundaries.mdc).

## Quick map (additions from this restructure)

| Path | Role |
| --- | --- |
| `aqp_platform/` | Hosted-platform deployment, build, IaC, cluster setup (single home: `deployments/`, `build/`, `deploy/`, `terraform/`, `compose/`, `configs/{deployment,terraform}/`, `scripts/cluster_install/`, root `Dockerfile`, `.dockerignore`). Also home to the [`aqp-ide/`](../../aqp_platform/deployments/kubernetes/aqp-ide/) single-pod K8s overlay (Phase A) + `theia-cloud/` Phase B scaffolding. |
| `aqp_ide/` | White-labeled Eclipse Theia 1.72 distribution + **six** AQP compile-time extensions (`aqp` / `aqp-shell` / `aqp-mcp-bridge` / `aqp-research-copilot` / `aqp-notebook-quant` / `aqp-quant`) + an MCP-driven research copilot + a FINOS Perspective Arrow notebook MIME renderer. Browser-target only. Canonical operator entrypoint is `aqp-cli ide`. |
| `aqp_cli/` | Standalone operator CLI. Includes the [`ide`](../../aqp_cli/src/aqp_cli/commands/ide.py) command group as the sanctioned production entrypoint for the AQP IDE. |
| `aqp_admin/` | Internal admin (managed services + company accounts). |
| `aqp_index/` | Curator-owned single source of truth. |
| `aqp_docs/` | Canonical AQP documentation (renamed from `docs/`). Now also hosts the AQP IDE SSoT pair: [`aqp-ide.md`](../../aqp_docs/aqp-ide.md) + [`aqp-ide-roadmap.md`](../../aqp_docs/aqp-ide-roadmap.md). |

These are additive. The pre-existing split between `aqp/`, `aqp_client/`,
`aqp_control_plane/`, `aqp_platform_core/`, `aqp_bots/`, `aqp_rl/`,
`aqp_models/`, and `aqp_snippets/` is unchanged.

## Per-package boundary contracts

| Package | Boundary contract | AGENTS file |
| --- | --- | --- |
| `aqp_ide/` | No `agentic_quant_platform` source imports into Theia TypeScript; cross HTTP only (`AqpApiService`) or via the DataMCP / CodebaseMCP HTTP surfaces. AQP code lives only under `theia-extensions/aqp*/`. Copilot LLM calls go through `router_complete` (rule 2); MCP registrations carry per-MCP `aud` (rule 49). | [../../aqp_ide/AGENTS.md](../../aqp_ide/AGENTS.md) |

## Hosted-platform paths now consolidated

Anything that builds, deploys, or manages a hosted AQP backend service
lives under `aqp_platform/`. The original root-level locations are gone:

- root `deployments/` -> `aqp_platform/deployments/`
- root `build/` -> `aqp_platform/build/`
- root `deploy/` -> `aqp_platform/deploy/`
- root `terraform/` -> `aqp_platform/terraform/`
- root `Dockerfile` -> `aqp_platform/Dockerfile`
- root `.dockerignore` -> `aqp_platform/.dockerignore`
- root `docker-compose.yml`, `docker-compose.platform.yml`, `docker-compose.viz.yml` -> `aqp_platform/compose/`
- `configs/deployment/` -> `aqp_platform/configs/deployment/`
- `configs/terraform/` -> `aqp_platform/configs/terraform/`
- `scripts/cluster_install/` -> `aqp_platform/scripts/cluster_install/`
