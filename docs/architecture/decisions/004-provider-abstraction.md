# ADR 004 — Abstract InfrastructureProvider ABC for workload runtime ops

- **Status**: Accepted (2026-05-18)
- **Authors**: Platform team
- **Supersedes**: Tightens AGENTS hard rule 42
- **Related**: [ADR 005 — separated control plane](005-separated-control-plane.md), [`AGENTS.md`](../../../AGENTS.md)

## Context

AQP's existing IaC story is Terraform-first (AGENTS hard rule 42): every state-mutating cluster operation goes through `aqp/terraform/runtime.py::TerraformRuntime`. That guarantee is great for **provisioning** (create cluster, create namespace, apply RBAC, register Auth0 tenant) but it's an awkward fit for **live workload operations** — restarting a pod, scaling a Deployment, exec-ing a shell, tailing logs — which today incur a full `terraform plan` + `apply` round trip and write to `terraform_runs` even though no IaC actually changed.

The refactor introduces the `aqp_control_plane` micro-project that needs to support five backends (docker_compose, kubernetes, AWS, Azure, GCP). Two paths were considered:

1. **Translate every workload op into Terraform** — every restart becomes a Terraform `null_resource` + provisioner. Preserves the rule 42 ledger as a single source of truth, but turns Terraform into a glorified `kubectl` wrapper.
2. **Introduce a sibling abstraction** — `InfrastructureProvider` ABC with five implementations, each calling its backend's native SDK (kubernetes-client, docker SDK, boto3, azure-mgmt, google-cloud-run). Terraform stays for provisioning only.

## Decision

Adopt **path 2: an abstract `InfrastructureProvider` ABC** for runtime workload operations. Specifically:

```python
class InfrastructureProvider(ABC):
    @abstractmethod
    async def start(self, spec: DeploymentSpec) -> DeploymentStatus: ...

    @abstractmethod
    async def stop(self, service_id: str) -> DeploymentStatus: ...

    @abstractmethod
    async def scale(self, service_id: str, replicas: int) -> DeploymentStatus: ...

    @abstractmethod
    async def status(self, service_id: str) -> DeploymentStatus: ...

    @abstractmethod
    async def apply_config(self, service_id: str, config: dict) -> bool: ...

    @abstractmethod
    async def stream_metrics(self, service_id: str): ...  # async generator
```

Five concrete providers live under `aqp_control_plane/src/aqp_cp/providers/`:

- `docker_compose.py` — docker Python SDK + `docker compose` subprocess for multi-container profiles
- `kubernetes.py` — kubernetes-client/python (in-cluster + kubeconfig); Deployment apply, scale-to-0, ConfigMap patch, Metrics Server query
- `aws.py` — boto3; EKS delegates to `kubernetes.py`; ECS/Fargate via `update_service`; config sync via SSM Parameter Store
- `azure.py` — azure-mgmt; AKS delegates to `kubernetes.py`; ACI via container groups; config sync via App Configuration / Key Vault
- `gcp.py` — google-cloud SDKs; GKE delegates to `kubernetes.py`; Cloud Run via revision updates; config sync via Secret Manager

Each provider:
- Reads credentials from env vars only (`aqp_platform_core.credentials.CredentialResolver`).
- Translates `DeploymentSpec` to its backend's native API.
- Returns a normalised `DeploymentStatus`.
- Maps backend-specific exceptions to structured `{status, data, error}` envelopes.

## Amendment to AGENTS hard rule 42 (this PR)

Rule 42 changes from "all Terraform IaC lifecycle actions go through TerraformRuntime" to:

> 42. **All Terraform IaC PROVISIONING actions go through `aqp/terraform/runtime.py::TerraformRuntime`.** Cluster bootstrap, IAM, Auth0 tenant, namespaces, secrets, network policies, and Ingress class registration are all "provisioning". The `terraform_runs` ledger, the `terraform_stack_spec_versions` hash-lock, the kill-switch hook (`/terraform/halt`), and OPA policy enforcement all depend on it.

A new rule 45 covers the workload ops side:

> 45. **All runtime workload operations go through `aqp_control_plane.InfrastructureProvider` (via `WorkloadRuntime`).** Start, stop, scale, restart, exec, log-tail, and `apply_config` are workload ops. They never reach for Terraform. A new `workload_runs` ledger row is created per mutating action with full audit context (user_id, action, target, provider, timestamp) BEFORE the provider call executes.

## Consequences

**Positive**
- Restart latency drops from ~30 s (Terraform plan + apply) to ~200 ms (kubectl scale).
- The five providers are fully independent — each can be implemented + tested in parallel by an `orchestrate` fan-out (see plan §8.2).
- Terraform stays clean for IaC provisioning and immutable audit trails. The `terraform_runs` ledger remains the source of truth for "what infrastructure exists".
- The `aqp_control_plane` micro-project becomes a thin, testable layer with mocked SDKs in CI.
- Hard rule 27 (IdentityProvider), 28 (KubernetesAdapter), and the new ABC all follow the same self-registering metaclass pattern — consistent across the codebase.

**Negative**
- Two separate audit ledgers (`terraform_runs` + `workload_runs`) instead of one. Documented in `docs/operations/incident-response.md`.
- The five providers each take their own credential chain. Mitigated by `CredentialResolver` so service code never sees raw env vars.
- Provisioning vs runtime boundary is a soft line — adding a new namespace is provisioning, but auto-creating a per-tenant namespace at user signup is workload-ish. Each new operation requires an explicit choice; ADR 005 includes a decision tree.

## Alternatives considered

- **Translate every op into Terraform** — rejected. Operational cost of running `terraform apply` on every pod restart is prohibitive (~30 s p99), and Terraform's lock semantics serialise unrelated ops on the same workspace.
- **Use Crossplane** — investigated; rejected for now. Crossplane is excellent for declarative cloud APIs but adds a CRD layer and operator dependency for marginal value over the five-provider Python ABC. Revisit when AQP exceeds five backends.
- **Use Pulumi instead of Terraform** — out of scope. The existing `TerraformRuntime` works and is hash-locked; replacing it is a separate ADR.

## Implementation references

- ABC: `aqp_control_plane/src/aqp_cp/providers/base.py`
- Five providers: `aqp_control_plane/src/aqp_cp/providers/{docker_compose,kubernetes,aws,azure,gcp}.py`
- Workload ledger model: `aqp/persistence/models_workload.py` (new in this PR)
- Telemetry streaming: `aqp_control_plane/src/aqp_cp/services/telemetry.py`
- AGENTS rule 45: [`AGENTS.md`](../../../AGENTS.md) (this PR)
