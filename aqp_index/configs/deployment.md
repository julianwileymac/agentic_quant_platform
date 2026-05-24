# Deployment configs

> Last refreshed: 2026-05-24 by aqp-index-curator (trigger: AQP IDE
> enhancement — added the single-pod `aqp-ide/` overlay row, the
> Phase B `theia-cloud/` scaffolding, and the `AQP_THEIA_*` runtime
> env block).

| Config | Purpose | Owner |
| --- | --- | --- |
| [../../aqp_platform/configs/deployment/topology.yaml](../../aqp_platform/configs/deployment/topology.yaml) | Service topology (cluster / namespace / endpoints) | platform |
| [../../aqp_platform/configs/terraform/](../../aqp_platform/configs/terraform/) | TerraformStackSpec YAMLs | platform |
| [../../aqp_platform/deployments/](../../aqp_platform/deployments/) | Compose + Kubernetes manifests (canonical) | platform |
| [../../aqp_platform/deployments/kubernetes/aqp-ide/](../../aqp_platform/deployments/kubernetes/aqp-ide/) | Single-pod AQP IDE K8s overlay (namespace / configmap / secret-template / deployment / service / ingress / networkpolicy). Applied via `kubectl apply -k aqp_platform/deployments/kubernetes/aqp-ide/`. | platform |
| [../../aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/](../../aqp_platform/deployments/kubernetes/aqp-ide/theia-cloud/) | **Phase B scaffolding only** (DEFERRED until ≥2 isolated workspaces are needed). | platform |
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
| AQP IDE (Theia Node backend) | `AQP_THEIA_*` env block read by [aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts](../../aqp_ide/theia-extensions/aqp/src/node/aqp-config-endpoint.ts) and served on `GET /aqp/config` (no bake-time inlining; same image runs in dev / staging / prod). Source of truth for the env list: [`aqp_cli/src/aqp_cli/commands/ide.py::_THEIA_ENV_KEYS`](../../aqp_cli/src/aqp_cli/commands/ide.py). |
| AQP IDE (CLI entrypoint) | `AQP_CLI_THEIA_PORT` / `AQP_CLI_THEIA_URL` / `AQP_CLI_THEIA_WORKSPACE` / `AQP_CLI_THEIA_YARN_OFFLINE` / `AQP_CLI_THEIA_DOCKER_IMAGE` ([aqp_cli/src/aqp_cli/config.py](../../aqp_cli/src/aqp_cli/config.py)) |

## `AQP_THEIA_*` runtime env block

The Theia Node backend reads these on every request and serves them as
JSON on `GET /aqp/config` (no secrets — Auth0 SPA values are PKCE-safe
to expose). Default values live in
[../../aqp_ide/browser.Dockerfile](../../aqp_ide/browser.Dockerfile);
K8s overrides live in
[../../aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml](../../aqp_platform/deployments/kubernetes/aqp-ide/configmap-aqp.yaml).

| Env var | Purpose |
| --- | --- |
| `AQP_THEIA_AUTH0_DOMAIN` | Auth0 tenant domain (e.g. `your-tenant.us.auth0.com`) |
| `AQP_THEIA_AUTH0_CLIENT_ID` | Auth0 SPA `client_id` (public per PKCE) |
| `AQP_THEIA_AUTH0_AUDIENCE` | Must equal AQP backend's `AQP_AUTH_OIDC_AUDIENCE` |
| `AQP_THEIA_AUTH0_SCOPE` | Default `openid profile email offline_access` |
| `AQP_THEIA_AUTH0_REDIRECT_URI` | Defaults to `${AQP_THEIA_PUBLIC_ORIGIN}/` |
| `AQP_THEIA_AUTH0_ORGANIZATION` | Optional Auth0 Organization id |
| `AQP_THEIA_API_URL` | AQP FastAPI base URL |
| `AQP_THEIA_FRONTEND_URL` | AQP Vite frontend origin (for embedded `ManagementWidget` iframe) |
| `AQP_THEIA_PROVIDERS_URL` | Full URL of the BFF `/auth/providers` endpoint |
| `AQP_THEIA_PUBLIC_ORIGIN` | Public origin of the running Theia |
| `AQP_THEIA_MCP_DATA_URL` | Streamable HTTP endpoint of `aqp-data-mcp` |
| `AQP_THEIA_MCP_DATA_AUDIENCE` | Canonical URI of `aqp-data-mcp` (RFC 9728 PRM `aud`) |
| `AQP_THEIA_MCP_CODEBASE_URL` | Streamable HTTP endpoint of `aqp-codebase-mcp` |
| `AQP_THEIA_MCP_CODEBASE_AUDIENCE` | Canonical URI of `aqp-codebase-mcp` (RFC 9728 PRM `aud`) |
| `AQP_THEIA_SERA_ENABLED` | `true` to default code-focused copilot agents to SERA-32B |
| `AQP_THEIA_ROUTER_COMPLETE_PATH` | Override the default `/llm/router/complete` path (rare) |

## CI surfaces

- `.github/workflows/ci.yml` runs `kubectl kustomize aqp_platform/deployments/kubernetes/overlays/<env>` for dev/staging/prod.
- `.github/workflows/cd-prod.yml` builds + pushes the four hosted images using Dockerfiles under `aqp_platform/build/docker/<service>/` then applies `aqp_platform/deployments/kubernetes/overlays/prod`.
- `.github/workflows/cd-staging.yml` mirrors prod for the staging overlay.
- The AQP IDE image is built from `aqp_ide/browser.Dockerfile`; CI deployment goes via `kubectl apply -k aqp_platform/deployments/kubernetes/aqp-ide/`.
