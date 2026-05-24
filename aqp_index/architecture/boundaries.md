# Repository boundaries

> Last refreshed: 2026-05-23 (seed).

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
| `aqp_ide/` | Vendored Theia IDE workspace + AQP extension. |
| `aqp_cli/` | Standalone operator CLI. |
| `aqp_admin/` | Internal admin (managed services + company accounts). |
| `aqp_index/` | Curator-owned single source of truth. |
| `aqp_docs/` | Canonical AQP documentation (renamed from `docs/`). |

These are additive. The pre-existing split between `aqp/`, `aqp_client/`,
`aqp_control_plane/`, `aqp_platform_core/`, `aqp_bots/`, and
`aqp_snippets/` is unchanged.
