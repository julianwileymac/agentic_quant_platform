---
title: 'Adding a new InfrastructureProvider to aqp_control_plane'
summary: 'Add a provider when you need to manage workloads on a backend the existing five (`docker_compose`, `kubernetes`, `aws`, `azure`, `gcp`) dont cover. Examples: Nomad, Fly.io, Render, on-prem VMs via Sa...'
owner: sre-team
last_reviewed: 2026-05-25
audience: both
---

# Adding a new InfrastructureProvider to aqp_control_plane

Step-by-step guide for shipping a new `InfrastructureProvider` implementation (AGENTS rule 45 / ADR 004).

## When to add a new provider

Add a provider when you need to manage workloads on a backend the existing five (`docker_compose`, `kubernetes`, `aws`, `azure`, `gcp`) don't cover. Examples: Nomad, Fly.io, Render, on-prem VMs via Salt/Ansible.

## Checklist

### 1. Sketch the credential chain

What env vars does the backend's SDK read? How does it discover credentials in CI vs on a developer laptop vs in production?

Document this in your provider's `_check_credentials()` so the health probe can fail loudly when credentials are missing.

### 2. Create the provider module

```python
# aqp_control_plane/src/aqp_cp/providers/<name>.py
from aqp_platform_core.providers.protocol import (
    InfrastructureProvider,
    InfrastructureProviderError,
    InfrastructureProviderUnavailable,
    ProviderKind,
)
from aqp_platform_core.providers.registry import register_provider_class


@register_provider_class("<alias>", replace=True)
class MyProvider(InfrastructureProvider):
    provider_kind = ProviderKind.<NEW_KIND>
    provider_alias = "<alias>"

    async def health(self) -> ProviderHealth: ...
    async def start(self, spec: DeploymentSpec) -> DeploymentStatus: ...
    async def stop(self, service_id: str, *, namespace=None) -> DeploymentStatus: ...
    async def scale(self, service_id, replicas, *, namespace=None) -> DeploymentStatus: ...
    async def status(self, service_id: str, *, namespace=None) -> DeploymentStatus: ...
    async def list_deployments(self, *, namespace=None) -> list[DeploymentStatus]: ...

    # Optional — override if your backend supports it.
    async def get_config(self, service_id: str, *, namespace=None) -> ServiceConfig: ...
    async def apply_config(self, patch: ConfigMapPatch) -> bool: ...
    async def stream_metrics(self, service_id, *, namespace=None, interval_seconds=10.0): ...
```

### 3. Add a new `ProviderKind`

```python
# aqp_platform_core/src/aqp_platform_core/providers/protocol.py
class ProviderKind(str, Enum):
    DOCKER_COMPOSE = "docker_compose"
    KUBERNETES = "kubernetes"
    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    NOMAD = "nomad"  # <-- your new kind
```

### 4. Register in the bootstrap helper

```python
# aqp_control_plane/src/aqp_cp/providers/__init__.py
for module_name in (
    "aqp_cp.providers.docker_compose",
    "aqp_cp.providers.kubernetes",
    "aqp_cp.providers.aws",
    "aqp_cp.providers.azure",
    "aqp_cp.providers.gcp",
    "aqp_cp.providers.<name>",  # <-- add yours
):
    ...
```

### 5. Optional deps go in `pyproject.toml` extras

```toml
[project.optional-dependencies]
<name> = ["sdk-package>=X,<Y"]
all-providers = [
    "aqp-control-plane[docker_compose,kubernetes,aws,azure,gcp,<name>]",
]
```

### 6. Write contract tests

Two test files:

```python
# aqp_control_plane/tests/providers/test_<name>.py — unit tests over the
# translation helpers (e.g. spec_to_<backend>, response_to_status)

# aqp_control_plane/tests/providers/test_<name>_integration.py — full
# contract test against a mocked SDK (moto for AWS, MagicMock for others)
```

Reuse the assertion patterns in `test_docker_compose.py` and `test_kubernetes.py`.

### 7. Update the bootstrap registry test

```python
# tests/providers/test_registry.py
def test_bootstrap_registers_all() -> None:
    registry = bootstrap()
    for expected in ("docker_compose", "kubernetes", "aws", "azure", "gcp", "<name>"):
        assert expected in registry.aliases()
```

### 8. Update the README + this runbook

Add your provider to the table in [`aqp_control_plane/README.md`](https://github.com/julianwileymac/agentic_quant_platform/blob/main/aqp_control_plane/README.md) and the per-cloud sections below.

## Per-cloud setup notes

### AWS

- Active provider: `AQP_CP_PROVIDER=aws`
- Credentials: standard boto3 chain (env vars / `~/.aws/credentials` / EC2 / EKS pod identity / WebIdentity)
- IAM minimum: `ecs:DescribeServices`, `ecs:UpdateService`, `ssm:GetParameter*`, `ssm:PutParameter*`, plus EKS read perms when using the K8s sub-path

### Azure

- Active provider: `AQP_CP_PROVIDER=azure`
- Credentials: `azure-identity` chain (env vars / Managed Identity / federated identity / Azure CLI)
- IAM minimum: Contributor on the AKS / Container Instances resource group

### GCP

- Active provider: `AQP_CP_PROVIDER=gcp`
- Credentials: `GOOGLE_APPLICATION_CREDENTIALS` env var pointing to a service account JSON, OR Workload Identity (preferred in production)
- IAM minimum: `run.developer`, `container.developer`, `secretmanager.admin` (per project)

## Definition of done

- [ ] Provider class registered + `provider_kind` matches alias
- [ ] All seven abstract methods implemented (or raise `InfrastructureProviderUnavailable` with a structured message)
- [ ] Credential probe in `health()` returns a useful error when creds are missing
- [ ] Unit tests + contract tests passing
- [ ] `tests/providers/test_registry.py` updated
- [ ] README + this runbook updated
- [ ] CI matrix builds + tests with the new optional dep group
