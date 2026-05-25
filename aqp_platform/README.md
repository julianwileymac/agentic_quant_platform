# aqp_platform

Hosted-platform deployment, build, IaC, and cluster-setup assets for the
[Agentic Quant Platform](../README.md). One folder, one home for every
artefact that builds, deploys, or manages the AQP backend services.

## What lives here

| Subfolder | Purpose |
| --- | --- |
| [deployments/](deployments/) | docker-compose stacks + Kubernetes manifests (base + overlays + helm) |
| [build/](build/) | Multi-arch Dockerfiles + config-generation helpers |
| [deploy/](deploy/) | Legacy / edge component configs (otel collector, superset, trino, vector, victoriametrics, k8s extras) |
| [terraform/](terraform/) | Terraform modules + environment workspaces (canonical IaC) |
| [compose/](compose/) | The three root-level docker-compose files (legacy bypass + viz + platform overlays) |
| [configs/](configs/) | Deployment-time YAML configs (`configs/deployment/topology.yaml`, `configs/terraform/*.yaml`) |
| [scripts/](scripts/) | Cluster install scripts (Loki, kube-prometheus-stack, QuestDB, Redpanda, etc.) |
| `Dockerfile` | Multi-stage root API/worker/paper/ingester image |
| `.dockerignore` | Build-context exclusions paired with the Dockerfile |

## Boundary

`aqp_platform/` is **infra + IaC + build tooling**. It is NOT a Python
runtime package and never appears in an `import aqp.*` line. The
runtime that consumes everything here lives in:

- [../aqp/](../aqp/) (monolith runtime)
- [../aqp_control_plane/](../aqp_control_plane/) (standalone control plane)
- [../aqp_platform_core/](../aqp_platform_core/) (shared contracts)

## Canonical workflows

### Local dev (Compose, via Makefile)

```bash
make generate-config ENV=local            # render aqp_platform/deployments/compose/.env.local
make dev                                  # compose up -d (base + local + override)
make stop                                 # compose down
make logs-svc SERVICE=aqp-core            # tail one service
```

### Legacy compose bypass

```bash
make up-compose-legacy                    # docker compose -f aqp_platform/compose/docker-compose.yml up -d
make down-compose-legacy
make logs-compose-legacy
```

### Build images (multi-arch)

```bash
make build                                # build aqp-client / aqp-cp / aqp-worker / aqp-ingestion
make build-cp                             # one image
```

### Terraform (via the AQP CLI - AGENTS rule 42)

```bash
aqp deploy plan
aqp deploy up                             # creates a workspace + apply via TerraformRuntime
aqp deploy status
aqp deploy logs api
aqp deploy down --yes
```

### Kubernetes (after a build)

```bash
kubectl kustomize aqp_platform/deployments/kubernetes/overlays/dev | kubectl apply -f -
```

CI flow (see [.github/workflows/](../.github/workflows/)):

- `ci.yml`: lints + tests, runs `kubectl kustomize aqp_platform/deployments/kubernetes/overlays/<env>` for dev/staging/prod.
- `cd-staging.yml` / `cd-prod.yml`: build + push images, then apply the matching overlay.

## Hard boundaries (enforced in [AGENTS.md](AGENTS.md))

1. **No `import aqp.*`** in this tree. Build tooling and IaC stay
   independent of the Python runtime.
2. **`TerraformRuntime` is the only sanctioned `terraform apply` path**
   (AQP hard rule 42). The runner is at
   [../aqp/terraform/runner.py](../aqp/terraform/runner.py); CI never
   shells out to `terraform` directly.
3. **`CredentialResolver` is the only credential surface** (AQP hard
   rule 26). No secret values in compose env, Helm values, or `*.tf`
   files. Inject via `ExternalSecret` -> `ClusterSecretStore` ->
   Vault / cloud secret manager.
4. **Multi-arch images** for every Dockerfile that lands here
   (`linux/amd64 + linux/arm64`). The base image uses
   `ARG BUILDPLATFORM` / `ARG TARGETPLATFORM` so the same Dockerfile
   builds for x86 cloud nodes and Raspberry Pi 5 edge nodes.
5. **Domain isolation**: AQP owns `aqp.fund`, `api.aqp.fund`,
   `manage.aqp.fund`. Cloudflare tunnels, Auth0 tenants, and
   Cloudflare Access apps in this tree are AQP-only - never mix with
   the portal's `julianwiley.com` (which lives in the sibling
   `rpi_kubernetes` repo).

## Related docs

- [../aqp_docs/docs/concepts/identity/management-engine.md](../aqp_docs/docs/concepts/identity/management-engine.md) - WorkloadRuntime + InfrastructureProvider design
- [../aqp_docs/docs/concepts/infrastructure/terraform-control-plane.md](../aqp_docs/docs/concepts/infrastructure/terraform-control-plane.md) - TerraformRuntime, spec hashing, OPA policy
- [../aqp_docs/docs/concepts/infrastructure/kubernetes-rpi-deployment.md](../aqp_docs/docs/concepts/infrastructure/kubernetes-rpi-deployment.md) - Edge cluster topology
- [../aqp_docs/docs/how-to/operations/](../aqp_docs/docs/how-to/operations/) - Runbooks for deploy / rollback / incident response
- [../aqp_index/index.md](../aqp_index/index.md) - Curator-owned project index
