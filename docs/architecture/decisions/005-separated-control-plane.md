# ADR 005 — Separated `aqp_control_plane/` micro-project

- **Status**: Accepted (2026-05-18)
- **Authors**: Platform team
- **Supersedes**: Embeds in `aqp/api/routes/control_plane.py`
- **Related**: [ADR 002](002-single-container-client.md), [ADR 003](003-auth0-zero-trust.md), [ADR 004](004-provider-abstraction.md)

## Context

The in-flight `aqp/api/routes/control_plane.py` exposes deploy / destroy / restart / logs endpoints to the Vite Control Plane UI. It already covers the "local k3d" and "rpi_kubernetes" targets and delegates mutating ops to `TerraformRuntime` via Celery tasks (see [`aqp/api/routes/control_plane.py`](../../../aqp/api/routes/control_plane.py)).

The refactor wants the control plane to:

1. Speak five backends (docker_compose, kubernetes, AWS, Azure, GCP) — not just two Terraform stacks.
2. Be deployable on its own (`/deployments/compose/docker-compose.admin.yml`, isolated `aqp-admin` Docker network) so an operator can run "just the control plane" against a remote cluster.
3. Be releasable independently from the AQP monolith (different cadence, different SLOs).
4. Have a security boundary that doesn't bleed in if `aqp` itself is compromised — and vice versa.

The strict-isolation reading of the prompt's hard constraint ("Never import `aqp.*` modules inside `aqp_control_plane/`") plus the existing `aqp/` codebase yields three integration patterns:

1. **Strict separation** — duplicate every model, validator, and adapter into `aqp_control_plane/`. 2x code, fully independent release.
2. **Shared lower-level library** — extract reusable bits (Pydantic topology models, JWT validator, K8s adapter ABCs, credential protocol) into a NEW `aqp_platform_core/` package both `aqp/` and `aqp_control_plane/` depend on. No `aqp.*` imports in CP, but shared lower-level code stays DRY.
3. **Evolve in place** — keep control plane in `aqp/`; just add the `aqp_client` container + Auth0 RBAC.

## Decision

Adopt **pattern 2** — the **shared-library** approach.

1. New top-level package `aqp_platform_core/` is created with its own `pyproject.toml` (installable as `aqp-platform-core`).
2. Move (with back-compat re-exports from `aqp/`) the following into `aqp_platform_core/`:
   - `topology/` — Pydantic models from `aqp/deployment/topology.py` (data classes only; loaders stay in `aqp/`).
   - `auth/` — Auth0 JWT validator from `aqp/auth/providers/auth0.py` + `aqp/api/security.py`'s claim validation + new `resource_filter.py` (ADR 003).
   - `kubernetes/` — `KubernetesAdapter` ABC from `aqp/kubernetes/protocol.py`. Concrete adapters (`InClusterAdapter`, `LocalComposeAdapter`, `RpiClusterAdapter`) stay in `aqp/`.
   - `credentials/` — `SecretStore` protocol + `CredentialResolver` interface. Concrete stores stay in `aqp/`.
   - `connectivity/` — NEW `ConnectivityConfig` Pydantic settings model with `AQP_*_URL` matrix.
   - `models/` — `DeploymentSpec`, `DeploymentStatus`, `MetricPoint`, `NodeHealth` (referenced by both `aqp.api.routes.control_plane` and the new `aqp_control_plane.api.routers`).
3. The `aqp_control_plane/` micro-project (own `pyproject.toml`) depends ONLY on `aqp-platform-core`. It never imports `aqp.*`.
4. `aqp/` keeps the runtimes, ledger writers, registry implementations, and concrete adapters. It also depends on `aqp-platform-core` (just like `aqp_control_plane/`).
5. Back-compat shims in `aqp/deployment/`, `aqp/auth/`, `aqp/kubernetes/`, `aqp/credentials/` re-export from `aqp_platform_core` so no existing import paths break and no other AQP module needs to change in this PR.

The strict-isolation enforcement is a CI lint:

```bash
# .github/workflows/ci.yml step
rg --type python "^from aqp(\.|$)|^import aqp(\.|$)" aqp_control_plane/ \
  && echo "FAIL: aqp_control_plane imports forbidden aqp.* module" && exit 1
```

## Consequences

**Positive**
- `aqp_control_plane` ships as a standalone OCI image with no AQP runtime dependency. Operators running multiple AQP tenants share one control plane.
- The shared lib is small (~2 kloc) and changes infrequently. When it does change, both `aqp/` and `aqp_control_plane/` re-pin and re-test — explicit coupling.
- The existing `aqp/api/routes/control_plane.py` becomes a thin proxy that calls the external `aqp_control_plane` when the env var `AQP_CP_REMOTE=1` is set, or talks in-process to the same modules when disabled. Backward compat for local dev.
- AGENTS hard rules 27 (IdentityProvider), 28 (KubernetesAdapter) still apply — the metaclass registries live in `aqp_platform_core/auth/` and `aqp_platform_core/kubernetes/`, with concrete impls registered from `aqp/` and `aqp_control_plane/` alike.

**Negative**
- Adds one more package to publish and version. Mitigated by treating `aqp-platform-core` as an internal dependency pinned to a git SHA from a monorepo — no PyPI release needed.
- Cross-package refactors now need to touch two `pyproject.toml` files. Acceptable cost; the boundary is intentional.
- The "embed vs separate" decision is now load-bearing for security — a vulnerability in `aqp_platform_core/auth/` lands in both planes. Reviewed in `ce-security-sentinel` agent runs (see `.cursor/agents/`).

## Alternatives considered

- **Strict separation (pattern 1)** — rejected. Duplicate code rots out of sync; security fixes have to land twice; impossible to keep JWT validator semantics identical between the two planes.
- **Evolve in place (pattern 3)** — rejected. The biggest gap the prompt closes is *deployment independence* and the *5-backend abstraction*. Both demand a separate process; in-place is just a renamed router.
- **gRPC contract between the two** — rejected for now. The two planes share Pydantic models and HTTP/JSON is already understood. gRPC adds proto-gen tooling burden without buying anything until we hit hundreds of req/s of internal calls.

## Decision tree: which side does new code go on?

When adding a new feature, ask:

1. Is this a workload runtime operation (start, stop, scale, exec, logs, telemetry)? → **`aqp_control_plane/`**
2. Is this an IaC provisioning operation (create cluster, register Auth0 tenant, apply RBAC)? → **`aqp/terraform/`**
3. Is this AQP business logic (agents, RL, bots, analysis, backtests)? → **`aqp/`**
4. Is this a shared model, validator, or ABC that BOTH need? → **`aqp_platform_core/`**

If unsure, prefer **`aqp/`** and revisit the boundary once the requirement is clearer.

## Implementation references

- Shared lib: `aqp_platform_core/` (this PR)
- Micro-project: `aqp_control_plane/` (this PR)
- Strict-isolation lint: `.github/workflows/ci.yml` (Phase 8)
- Existing in-AQP control plane: `aqp/api/routes/control_plane.py`
- Existing topology: `aqp/deployment/topology.py`
- AGENTS rules 27, 28, 42, 45 — boundary owners
