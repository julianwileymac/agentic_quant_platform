# Deployment configs

> Last refreshed: 2026-05-23 (seed).

| Config | Purpose | Owner |
| --- | --- | --- |
| [../../configs/deployment/topology.yaml](../../configs/deployment/topology.yaml) | Service topology (cluster / namespace / endpoints) | platform |
| [../../configs/agents/](../../configs/agents/) | AgentSpec YAMLs | runtime |
| [../../configs/rl/](../../configs/rl/) | RL specs (data pipelines, rewards, agents) | rl |
| [../../configs/strategies/](../../configs/strategies/) | Strategy + alpha YAMLs | strategy |
| [../../configs/ml/](../../configs/ml/) | ML model YAMLs | ml |
| [../../configs/terraform/](../../configs/terraform/) | TerraformStackSpec YAMLs | platform |
| [../../deployments/](../../deployments/) | Compose + Kubernetes manifests | platform |

## Overrides

| Layer | Mechanism |
| --- | --- |
| Settings | `AQP_*` env vars (read once via `aqp.config.settings`, AGENTS rule 7) |
| Topology | `configs/deployment/topology.yaml` -> [aqp/config/topology_fallback.py](../../aqp/config/topology_fallback.py) -> Settings fields |
| Provider selection | `AQP_PROVIDER` (see [aqp_control_plane/](../../aqp_control_plane/) settings) |
| Identity | `AQP_AUTH_*` (see [../../aqp_docs/identity.md](../../aqp_docs/identity.md)) |
