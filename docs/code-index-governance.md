# Code Index Governance

Status: active.

This document explains how agents should search and index AQP during the
repository split. The goal is to keep edits inside the right future project
boundary before source code is physically separated.

## Search Order

1. Read the nearest `AGENTS.md` for the folder being edited.
2. Read `docs/repository-split.md` to identify the owning domain.
3. Search within the owning domain first.
4. Only broaden to `aqp/` or repo root when the boundary document says the
   implementation still lives there.
5. Record new reusable patterns in `aqp_snippets/` or `.cursor/skills/`
   instead of scattering notes across unrelated docs.

## Domain Index

| Domain | Start here | Notes |
| --- | --- | --- |
| Control plane | `aqp_control_plane/AGENTS.md` | `/manage/*`, providers, workload lifecycle |
| Platform core | `aqp_platform_core/AGENTS.md` | Shared contracts only |
| Client | `aqp_client/AGENTS.md`, `aqp_client/AGENTS.md` | Active source remains in `aqp_client/` |
| Snippets | `aqp_snippets/AGENTS.md` | Reference-only curated knowledge |
| Bots | `aqp_bots/AGENTS.md` | Runtime remains in `aqp/bots/` for now |
| Runtime monolith | `AGENTS.md` | Agents, RL, data, backtests, persistence, tasks |

## Indexing Rules

- Codebase MCP indexes must respect workspace allow-lists and secret
  deny-lists from `aqp/codebase/mcp/policy.py`.
- Generated indexes should not include `.env`, private keys, kubeconfigs,
  token files, model weights, or local warehouse data.
- Agent-readable docs should link to paths, not line numbers, unless the
  output is a transient review.
- Keep split-boundary indexes short enough that agents can read them before
  editing.

## Boundary Checks

Use these searches before a boundary-sensitive change:

```bash
rg --type py "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/src
rg "aqp_snippets|extractions|inspiration" aqp aqp_control_plane aqp_platform_core
rg "control.local/api|management/backend|management/frontend" docs README.md
```

The first command must return no matches. The second and third commands may
return documented migration references, but should not reveal runtime imports
or active instructions that route new work to deprecated surfaces.

