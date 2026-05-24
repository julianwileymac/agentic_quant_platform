# AGENTS.md

Agent contract for `aqp_platform`.

## Purpose

Single home for hosted-platform deployment, build, IaC, cluster setup, and
runtime orchestration assets. NOT a Python runtime package; never imported
from `aqp.*`. Consumed by the Makefile, by CI workflows, and by the AQP
control-plane through `TerraformRuntime` + `WorkloadRuntime`.

## Hard Boundaries

1. **No `import aqp.*`** in this tree. This folder is build tooling +
   IaC + Kubernetes / Compose manifests + helper scripts. The runtime
   that consumes it lives in [../aqp/](../aqp/),
   [../aqp_control_plane/](../aqp_control_plane/), and
   [../aqp_platform_core/](../aqp_platform_core/).
2. **`TerraformRuntime` is the only sanctioned `terraform apply` path.**
   AQP hard rule 42 (`AGENTS.md`). Routes / Celery tasks / MCP tools
   wrap it; nothing calls `subprocess.run(["terraform", ...])` directly
   outside [../aqp/terraform/runner.py](../aqp/terraform/runner.py).
   CI workflows under [.github/workflows/](../.github/workflows/) use
   `aqp deploy` (which lands a `terraform_runs` row), never raw
   `terraform apply`.
3. **`CredentialResolver` is the only credential surface.** AQP hard
   rule 26. No secrets in compose env, Helm `values.yaml`, or Terraform
   variable files. Every secret flows through `ExternalSecret` ->
   `ClusterSecretStore` -> Vault / cloud secret manager. Hand-pasting a
   token into a manifest is a review-blocking change.
4. **Multi-arch image invariant.** Every Dockerfile in this tree builds
   for `linux/amd64 + linux/arm64`. Use `ARG BUILDPLATFORM` /
   `ARG TARGETPLATFORM`. The base image is the reference template
   ([Dockerfile](Dockerfile)).
5. **Domain isolation.** AQP-only hostnames live here:
   - `aqp.fund` - operator UI
   - `api.aqp.fund` - REST API
   - `manage.aqp.fund` - control-plane API
   Never co-mingle with `julianwiley.com` (portal lives in the sibling
   `rpi_kubernetes` repo). Different certs, different Cloudflare
   tunnels, different Auth0 tenants.
6. **`workload_runs` audit ledger.** Every workload action that lands
   through `WorkloadRuntime` (start/stop/scale/restart/exec/logs/
   apply_config/rotate_secret) MUST write a `workload_runs` row before
   executing. This is enforced inside `WorkloadRuntime`; never bypass.
7. **Hash-locked spec versions.** `TerraformStackSpec` ->
   `terraform_stack_spec_versions` (rule 43); `WorkflowSpec` ->
   `workflow_spec_versions` (rule 41). Resnapshotting on hash change
   creates a NEW row; never update in place.

## Where Changes Go

| Change | Location |
| --- | --- |
| New Kubernetes manifest | `deployments/kubernetes/base/` or matching overlay |
| New Helm chart | `deployments/kubernetes/helm/<chart>/` |
| New compose service | `deployments/compose/docker-compose.<env>.yml` (canonical) or `compose/` (legacy bypass) |
| New Terraform module | `terraform/modules/<module>/` + matching environment |
| Terraform module template (Jinja2) | `../aqp/terraform/codegen/templates/<kind>.tf.j2` (rule 42) |
| New base-image change | [Dockerfile](Dockerfile) (multi-stage) |
| New per-service Dockerfile | `build/docker/<service>/Dockerfile` |
| Config-generation logic | `build/scripts/generate_config.py` |
| Deployment-time YAML | `configs/deployment/topology.yaml` (single source of truth) |
| Terraform stack YAML | `configs/terraform/<env>.yaml` |
| Cluster install script | `scripts/cluster_install/install-<component>.sh` |
| New observability backend config | `deploy/<component>/...` (legacy/edge) |

## Validation

```bash
# Compose lint - confirm every compose file parses + references valid
# Dockerfiles / contexts:
docker compose -f aqp_platform/compose/docker-compose.yml config > /dev/null
docker compose -f aqp_platform/compose/docker-compose.platform.yml config > /dev/null
docker compose -f aqp_platform/compose/docker-compose.viz.yml config > /dev/null

# Kustomize build for every overlay:
for env in dev staging prod; do
  kubectl kustomize aqp_platform/deployments/kubernetes/overlays/$env > /tmp/$env.yaml
  kubectl apply --dry-run=client -f /tmp/$env.yaml
done

# Terraform fmt + validate (NEVER terraform apply directly):
cd aqp_platform/terraform
terraform fmt -check -recursive
for env in aqp_platform/terraform/environments/*/; do
  cd $env
  terraform init -backend=false
  terraform validate
  cd -
done

# Required guard: aqp_platform MUST NOT import aqp runtime:
rg --type py "^(from|import)\s+aqp(\.|\s|$)" aqp_platform/build/scripts \
   | grep -vE 'aqp_platform_core' && exit 1 || true
```

## Subagents you SHOULD invoke

- [aqp-management-engine](../.cursor/agents/aqp-management-engine.md) -
  for any direct-control workload action (start / stop / scale / exec /
  rotate-secret).
- [aqp-kubernetes-deployment-auditor](../.cursor/agents/aqp-kubernetes-deployment-auditor.md) -
  for any change to deployment topology, Helm values, or overlay
  kustomizations.
- [aqp-k8s-docker-implementer](../.cursor/agents/aqp-k8s-docker-implementer.md) -
  for KubernetesAdapter / Docker SDK changes that ripple here.
- [aqp-index-curator](../.cursor/agents/aqp-index-curator.md) - MUST be
  invoked (or a debt note opened) after every commit that touches this
  tree per [aqp-index-reflect.mdc](../.cursor/rules/aqp-index-reflect.mdc).
