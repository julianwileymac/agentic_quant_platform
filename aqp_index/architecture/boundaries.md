# Repository boundaries

> Last refreshed: 2026-05-23 (aqp_platform extraction).

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
| `aqp_platform/` | Hosted-platform deployment, build, IaC, cluster setup (single home: `deployments/`, `build/`, `deploy/`, `terraform/`, `compose/`, `configs/{deployment,terraform}/`, `scripts/cluster_install/`, root `Dockerfile`, `.dockerignore`). |
| `aqp_ide/` | Vendored Theia IDE workspace + AQP extension. |
| `aqp_cli/` | Standalone operator CLI. |
| `aqp_admin/` | Internal admin (managed services + company accounts). |
| `aqp_index/` | Curator-owned single source of truth. |
| `aqp_docs/` | Canonical AQP documentation (renamed from `docs/`). |

These are additive. The pre-existing split between `aqp/`, `aqp_client/`,
`aqp_control_plane/`, `aqp_platform_core/`, `aqp_bots/`, and
`aqp_snippets/` is unchanged.

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
