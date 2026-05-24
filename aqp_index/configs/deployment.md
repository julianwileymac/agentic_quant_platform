# Deployment configs

> Last refreshed: 2026-05-23 (aqp_platform extraction).

| Config | Purpose | Owner |
| --- | --- | --- |
| [../../aqp_platform/configs/deployment/topology.yaml](../../aqp_platform/configs/deployment/topology.yaml) | Service topology (cluster / namespace / endpoints) | platform |
| [../../aqp_platform/configs/terraform/](../../aqp_platform/configs/terraform/) | TerraformStackSpec YAMLs | platform |
| [../../aqp_platform/deployments/](../../aqp_platform/deployments/) | Compose + Kubernetes manifests (canonical) | platform |
| [../../aqp_platform/compose/](../../aqp_platform/compose/) | Root-level docker-compose files (legacy bypass + viz + platform overlays) | platform |
| [../../aqp_platform/terraform/](../../aqp_platform/terraform/) | Terraform modules + environment workspaces | platform |
| [../../aqp_platform/build/](../../aqp_platform/build/) | Multi-arch Dockerfiles + `generate_config.py` + `sync_auth0_env_to_k8s.py` | platform |
| [../../aqp_platform/deploy/](../../aqp_platform/deploy/) | Legacy / edge component configs (otel, superset, trino, vector, victoriametrics, k8s extras) | platform |
| [../../aqp_platform/scripts/cluster_install/](../../aqp_platform/scripts/cluster_install/) | Helm install scripts for shared infra | platform |
| [../../configs/agents/](../../configs/agents/) | AgentSpec YAMLs | runtime |
| [../../configs/rl/](../../configs/rl/) | RL specs (data pipelines, rewards, agents) | rl |
| [../../configs/strategies/](../../configs/strategies/) | Strategy + alpha YAMLs | strategy |
| [../../configs/ml/](../../configs/ml/) | ML model YAMLs | ml |

## Overrides

| Layer | Mechanism |
| --- | --- |
| Settings | `AQP_*` env vars (read once via `aqp.config.settings`, AGENTS rule 7) |
| Topology | `aqp_platform/configs/deployment/topology.yaml` -> [aqp/config/topology_fallback.py](../../aqp/config/topology_fallback.py) -> Settings fields |
| Topology override path | `AQP_DEPLOYMENT_TOPOLOGY_PATH` env var |
| Provider selection | `AQP_PROVIDER` (see [aqp_control_plane/](../../aqp_control_plane/) settings) |
| Identity | `AQP_AUTH_*` (see [../../aqp_docs/identity.md](../../aqp_docs/identity.md)) |

## CI surfaces

- `.github/workflows/ci.yml` runs `kubectl kustomize aqp_platform/deployments/kubernetes/overlays/<env>` for dev/staging/prod.
- `.github/workflows/cd-prod.yml` builds + pushes the four hosted images using Dockerfiles under `aqp_platform/build/docker/<service>/` then applies `aqp_platform/deployments/kubernetes/overlays/prod`.
- `.github/workflows/cd-staging.yml` mirrors prod for the staging overlay.
