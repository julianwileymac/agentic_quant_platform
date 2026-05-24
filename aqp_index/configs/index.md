# Configuration index

> Last refreshed: 2026-05-23 (aqp_platform extraction).

## Canonical sources

- [../../configs/](../../configs/) - runtime YAML configs (strategies,
  agents, ML models, LLM profiles, RAG taxonomies, RL specs, paper
  trading, workflows).
- [../../aqp_platform/configs/](../../aqp_platform/configs/) -
  deployment-time YAML configs (`deployment/topology.yaml`,
  `terraform/*.yaml`).
- [../../aqp/config/settings.py](../../aqp/config/settings.py) - the
  single Pydantic settings class (AGENTS rule 7). Every `AQP_*` env var
  is a field. Topology fallback resolves
  `aqp_platform/configs/deployment/topology.yaml`.
- [../../.env.example](../../.env.example) - template for local `.env`.

## Sections

| Section | Purpose |
| --- | --- |
| [deployment.md](deployment.md) | Deployment topology + Terraform stack config map (now under `aqp_platform/configs/`) |

## Split between runtime and deployment configs

| Where | Owns |
| --- | --- |
| [../../configs/](../../configs/) | Per-runtime specs the AQP process loads at boot or on-demand (AgentSpec, BotSpec, RLExperimentSpec, AnalysisSpec, StrategyConfig, ...). |
| [../../aqp_platform/configs/](../../aqp_platform/configs/) | Deployment-time inputs the platform consumes BEFORE the AQP process exists (cluster topology, IaC stack params). |

## How to extend

Add a new file under `configs/` (runtime) only when a config domain
crosses three or more `aqp_*` packages or has a non-obvious overlay
pattern. Add a new file under `aqp_platform/configs/` (deployment) for
new cluster / topology / Terraform-stack inputs.
