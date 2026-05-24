# aqp_index debt — `aqp_rl` + `aqp_models` extraction

Status: pending curator pass.

## Context

On 2026-05-24 the AQP repository extracted two new top-level boundary
packages:

- [aqp_rl/](../../aqp_rl/) — RL subsystem (formerly `aqp/rl/`).
- [aqp_models/](../../aqp_models/) — custom model pulling / building /
  training / fine-tuning / evaluating / testing (formerly `aqp/ml/`,
  plus the `vllm_runner.py` and `ollama_client.py` slice of `aqp/llm/`).

The extraction follows the existing `aqp_bots/` / `aqp_platform_core/` /
`aqp_control_plane/` boundary pattern. Each new package owns:

- Source under `src/<pkg>/` (src-layout).
- Celery task wrapper(s) under `tasks/` (task `name=` strings preserved
  as `aqp.tasks.<file>.*` for in-flight queue compatibility).
- FastAPI router(s) under `api/routes/` (mount paths `/rl`, `/ml`,
  `/analytics/ml` unchanged).
- YAML spec library under `configs/`.
- Tests under `tests/`.
- Per-package `pyproject.toml`, `AGENTS.md`, `README.md`, `INDEX.md`.

Legacy import paths (`aqp.rl.*`, `aqp.ml.*`,
`aqp.llm.{vllm_runner,ollama_client}`) are preserved through
deprecation-warning compatibility shims under `aqp/rl/`, `aqp/ml/`, and
`aqp/llm/{vllm_runner,ollama_client}.py` per the strangler-migration
policy in [aqp_docs/repository-split.md](../../aqp_docs/repository-split.md).
The central LLM gateway (`router_complete`, memory, cache, prompts,
tokens) stays at [aqp/llm/](../../aqp/llm/) per Hard Rule 2 in the root
[AGENTS.md](../../AGENTS.md).

## Surfaces touched (qualifying for `aqp-index-reflect.mdc`)

- Root [README.md](../../README.md) — Repository Structure table updated.
- Root [AGENTS.md](../../AGENTS.md) — project map (boundary table + per-`aqp/`
  subpackage table) gained `aqp_rl/` and `aqp_models/` rows; legacy
  `aqp/rl/` and `aqp/ml/` rows downgraded to deprecated-shim status;
  hard rules **16, 17, 18, 19, 20, 36, 37, 38** swapped path citations
  to the new canonical paths; quick-reference and "Where to look for X"
  tables updated. Hard rule **2** (`router_complete`) untouched.
- [.cursor/rules/aqp.mdc](../rules/aqp.mdc) — scoped-rules table gained
  rows for `aqp_rl/**` and `aqp_models/**`.
- [.cursor/rules/runtimes.mdc](../rules/runtimes.mdc) — glob list
  expanded to include `aqp_rl/src/aqp_rl/**/*.py`,
  `aqp_rl/tests/**/*.py`, `aqp_rl/configs/**/*.yaml`; path citations in
  prose swapped.
- New: [.cursor/rules/aqp-rl.mdc](../rules/aqp-rl.mdc),
  [.cursor/rules/aqp-models.mdc](../rules/aqp-models.mdc).
- Updated path citations: [.cursor/rules/policy-backbones.mdc](../rules/policy-backbones.mdc),
  [.cursor/rules/optimal-control.mdc](../rules/optimal-control.mdc),
  [.cursor/rules/iceberg.mdc](../rules/iceberg.mdc),
  [.cursor/rules/agentic-rl.mdc](../rules/agentic-rl.mdc),
  [.cursor/rules/tasks-api.mdc](../rules/tasks-api.mdc),
  [.cursor/rules/mcp-risk.mdc](../rules/mcp-risk.mdc).
- [aqp_docs/repository-split.md](../../aqp_docs/repository-split.md) —
  Domain Map gained `aqp_rl` + `aqp_models` rows; Allowed Dependencies
  mermaid extended; Migration Order entries 6 + 7 added.
- [aqp_docs/aqp-monorepo-paths.md](../../aqp_docs/aqp-monorepo-paths.md)
  — added new responsibilities and the legacy → canonical mapping
  table.
- New top-level packages: [aqp_rl/](../../aqp_rl/),
  [aqp_models/](../../aqp_models/). Each has its own `AGENTS.md`,
  `README.md`, `INDEX.md`, `pyproject.toml`, plus the standard
  `src/<pkg>/`, `tasks/`, `api/routes/`, `configs/`, `tests/` siblings.

## What the curator should refresh

When the next `aqp-index-curator` pass runs, refresh these
`aqp_index/` surfaces (sole-writer boundary — only the curator may
edit):

- `aqp_index/architecture/boundaries.md` — add the two new boundaries
  next to `aqp_bots/`, `aqp_platform_core/`, `aqp_control_plane/`.
- `aqp_index/configs/index.md` — re-point the RL and ML config sets
  from `configs/rl/` / `configs/ml/` to `aqp_rl/configs/` /
  `aqp_models/configs/`.
- `aqp_index/configs/deployment.md` — same path swap.
- The token-saving code indices for RL and ML — re-scan from
  `aqp_rl/src/aqp_rl/` and `aqp_models/src/aqp_models/`.
- `aqp_index/index.md` (if it lists active boundaries) — add rows for
  the two new packages.
- The skills + subagent registries — note that
  `aqp-rl-runtime-expert` should now also fire on `aqp_rl/**`. (Plan
  is to keep that subagent and add a brief trigger note.)

## Why this is a debt note instead of an in-place refresh

The extraction itself is large enough that the curator pass deserves a
dedicated commit rather than being bundled into the source-move /
governance-update commit. This note exists so the next curator
invocation has a complete, citable list of surfaces that changed.

## Deferred follow-ups (not executed in this PR)

These items showed up while pruning the root cruft. They were scoped
out of the rl/models extraction PR because each requires its own
consolidation pass:

1. **Root `inspiration/` is a 101,987-file duplicate of
   `aqp_snippets/inspiration/`.** The root copy is in `.gitignore`
   (untracked working directory) but physically present. Counts match
   exactly. A follow-up cleanup PR should delete the root duplicate.
2. **Root `extractions/` is a tracked near-duplicate of
   `aqp_snippets/extractions/`.** Root has 13 files, canon has 12 —
   minor delta is `README.md`. Both directories are tracked in git.
   AGENTS.md and `aqp_docs/aqp-monorepo-paths.md` both name
   `aqp_snippets/extractions/` as canonical; the root copy should
   merge in and be removed in a follow-up PR.
3. **Root `data/`, `notebooks/`, `design/`, `schemas/`** were not
   relocated. `data/` is a runtime state directory (Iceberg / MLflow /
   Chroma local stores) — should be `.gitignore`d if it is not
   already. `notebooks/` and `design/` and `schemas/` may belong
   under `aqp_docs/` or `aqp_snippets/` — confirm intent with the
   operator before moving.

## References

- Plan: `.cursor/plans/aqp_rl_aqp_models_extract_c61da021.plan.md`
- Strangler-migration policy:
  [aqp_docs/repository-split.md](../../aqp_docs/repository-split.md)
- Always-on rule that triggered this debt note:
  [.cursor/rules/aqp-index-reflect.mdc](../rules/aqp-index-reflect.mdc).
