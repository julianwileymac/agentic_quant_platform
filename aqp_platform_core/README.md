# aqp-platform-core

Shared, dependency-free Pydantic models + ABCs + protocols for the Agentic Quant Platform.

Depended on by both:

- [`aqp/`](../aqp/) — the AQP monolith (FastAPI API, Celery workers, four hash-locked spec runtimes, etc.)
- [`aqp_control_plane/`](../aqp_control_plane/) — the isolated control-plane micro-project (FastAPI service exposing the five `InfrastructureProvider` backends)

The boundary is enforced by CI (see `.github/workflows/ci.yml`): `aqp_control_plane/` must NOT import from `aqp/*`.

## What's inside

| Module                                | Purpose                                                                                  |
| ------------------------------------- | ---------------------------------------------------------------------------------------- |
| `aqp_platform_core.topology`          | Pydantic models for deployment topology (services, targets, clusters, auth, terraform)   |
| `aqp_platform_core.auth`              | Auth0 JWT validator (JWKS + RS256), resource filter, scope grid, claim namespace helpers |
| `aqp_platform_core.kubernetes`        | `KubernetesAdapter` ABC + value types (`PodInfo`, `PodLogEvent`, `PodExecResult`)        |
| `aqp_platform_core.credentials`       | `SecretStore` protocol + `Credential` / `CredentialKey` value types                      |
| `aqp_platform_core.connectivity`      | `ConnectivityConfig` settings model — `AQP_*_URL` matrix for the proxy gateway           |
| `aqp_platform_core.models`            | Wire-format models (`DeploymentSpec`, `DeploymentStatus`, `MetricPoint`, `NodeHealth`)   |
| `aqp_platform_core.providers`         | `InfrastructureProvider` ABC + metaclass (replaces `TerraformRuntime` for workload ops)  |

## Design rules

1. **Never import from `aqp.*`.** This package is the SHARED foundation. Importing from `aqp/` would make `aqp_control_plane/` transitively depend on `aqp/`.
2. **Minimal runtime dependencies.** Only `pydantic`, `httpx`, `python-jose`, `cryptography`, `PyYAML`. No FastAPI, no SQLAlchemy, no Celery.
3. **Pure ABCs and value types.** Side effects (registry calls, network IO at import time) belong in `aqp/` or `aqp_control_plane/`, not here.
4. **Stable wire format.** Adding fields to `DeploymentSpec` / `DeploymentStatus` / `MetricPoint` is fine; renaming or removing them is a major version bump.

## Install

```bash
# From within the agentic_quant_platform monorepo:
pip install -e ./aqp_platform_core[dev]
```

## Test

```bash
cd aqp_platform_core
pytest -ra
```
