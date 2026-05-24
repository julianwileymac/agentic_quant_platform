# AQP Monorepo Paths

Status: active.

Canonical path contract for this repository. Sibling repos (`rpi_kubernetes`,
`theia-ide`, `aqp_platform_admin`) mirror this table in their own
`aqp_docs/aqp-monorepo-paths.md` files.

| AQP responsibility | Path |
| --- | --- |
| Control plane | `aqp_control_plane/` |
| Shared platform contracts | `aqp_platform_core/` |
| Active client (Vite) | `aqp_client/` |
| Bot runtime/templates | `aqp_bots/` |
| Snippet corpus | `aqp_snippets/` |
| Monolith runtime | `aqp/` |
| Standalone operator CLI | `aqp_cli/` |
| Internal admin (services + accounts) | `aqp_admin/` |
| Vendored Theia IDE workspace | `aqp_ide/` |
| Curator-owned project index (SSoT) | `aqp_index/` |
| Canonical documentation | `aqp_docs/` |
| Hosted-platform single home | `aqp_platform/` |
| Kubernetes workloads | `aqp_platform/deployments/kubernetes/` |
| Terraform modules + environments | `aqp_platform/terraform/` |
| Multi-arch Dockerfiles + config gen | `aqp_platform/build/` |
| Legacy / edge component configs | `aqp_platform/deploy/` |
| Root-level compose files | `aqp_platform/compose/` |
| Multi-stage root Dockerfile | `aqp_platform/Dockerfile` |
| Deployment topology YAML | `aqp_platform/configs/deployment/topology.yaml` |
| Terraform stack YAMLs | `aqp_platform/configs/terraform/` |
| Cluster install scripts | `aqp_platform/scripts/cluster_install/` |

Compatibility stubs and historical paths (do not add active source here):

| Legacy path | Points to |
| --- | --- |
| `frontend/` | `aqp_client/` |
| `extractions/` | `aqp_snippets/extractions/` |
| `inspiration/` | `aqp_snippets/inspiration/` (ignored raw repos) |
| `aqp/bots/` | `aqp_bots/` (import shim) |
| `docs/` | `aqp_docs/` (renamed; all references updated) |
| root `deployments/` | `aqp_platform/deployments/` |
| root `build/` | `aqp_platform/build/` |
| root `deploy/` | `aqp_platform/deploy/` |
| root `terraform/` | `aqp_platform/terraform/` |
| root `Dockerfile` | `aqp_platform/Dockerfile` |
| root `.dockerignore` | `aqp_platform/.dockerignore` |
| root `docker-compose.yml` | `aqp_platform/compose/docker-compose.yml` |
| root `docker-compose.platform.yml` | `aqp_platform/compose/docker-compose.platform.yml` |
| root `docker-compose.viz.yml` | `aqp_platform/compose/docker-compose.viz.yml` |
| `configs/deployment/` | `aqp_platform/configs/deployment/` |
| `configs/terraform/` | `aqp_platform/configs/terraform/` |
| `scripts/cluster_install/` | `aqp_platform/scripts/cluster_install/` |
