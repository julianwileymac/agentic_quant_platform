# Configuration index

> Last refreshed: 2026-05-23 (seed).

## Canonical sources

- [../../configs/](../../configs/) - all YAML configs (strategies, agents,
  ML models, LLM profiles, RAG taxonomies, deployment topology).
- [../../aqp/config/settings.py](../../aqp/config/settings.py) - the single
  Pydantic settings class (AGENTS rule 7). Every `AQP_*` env var is a field.
- [../../.env.example](../../.env.example) - template for local `.env`.

## Sections

| Section | Purpose |
| --- | --- |
| [deployment.md](deployment.md) | Deployment topology + agents config map |

## How to extend

Add a new file under `configs/` only when a config domain crosses three
or more `aqp_*` packages or has a non-obvious overlay pattern (e.g. dev /
staging / prod overlays, runtime overrides via REST). Otherwise the
existing `configs/` README + the per-package AGENTS.md is enough.
