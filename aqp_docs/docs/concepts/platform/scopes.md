---
title: 'AQP Scope Catalogue'
summary: 'Every scope follows `<resource>:<action>` (kebab-case nouns and verbs, colon separator). The four ADR 003 infrastructure scopes (`read:infrastructure`, `manage:agents`, `manage:infrastructure`, `admin...'
owner: platform-team
last_reviewed: 2026-05-25
audience: both
---

# AQP Scope Catalogue

Single source of truth for every authorization scope used by the AQP
control plane. The canonical Python module is
[aqp/auth/scopes.py](../aqp/auth/scopes.py) (`AQPScope`); the canonical
Terraform Auth0 provisioning lives in
[aqp_platform/terraform/modules/auth0_identity/main.tf](../aqp_platform/terraform/modules/auth0_identity/main.tf)
(`local.scopes` + `local.role_permissions`); the canonical role lattice
is in
[aqp_platform_core/src/aqp_platform_core/auth/rbac.py](../aqp_platform_core/src/aqp_platform_core/auth/rbac.py)
(`_ROLE_LATTICE`). All three MUST stay in sync — the regression test at
`tests/auth/test_scopes.py` enforces it.

## Scope-string convention

Every scope follows `<resource>:<action>` (kebab-case nouns and verbs,
colon separator). The four ADR 003 infrastructure scopes
(`read:infrastructure`, `manage:agents`, `manage:infrastructure`,
`admin:cluster`) intentionally use a verb-first form for backward
compatibility with the original Phase 4 rollout; the AQP-specific
extensions added in Phase 1 of the control-plane maturation use the
canonical resource-first form.

The `platform:admin` scope is the implicit super-scope — any holder of
`platform:admin` satisfies any other scope check. It is granted only to
the `aqp-superadmin` role and used very rarely.

## Scope catalogue

### Data plane

| Scope | Description |
| --- | --- |
| `data:read` | Read AQP data and metadata (datasets, catalogs, lineage) |
| `data:write` | Mutate AQP data through sanctioned APIs |
| `admin:iceberg` | Drop, consolidate, or redefine Iceberg tables |

### Infrastructure (ADR 003 four-scope grid)

| Scope | Description |
| --- | --- |
| `read:infrastructure` | View deployment status, pods, logs, non-secret config |
| `manage:agents` | Start / stop / restart / scale assigned AQP agents and bot workloads |
| `manage:infrastructure` | Deploy and update AQP services and non-secret ConfigMaps within an assigned org |
| `admin:cluster` | Full cluster control + resource-scope bypass for AQP super-admins |

### Agents

| Scope | Description |
| --- | --- |
| `agent:view` | Inspect agent specs, runs, and telemetry |
| `agent:execute` | Invoke or schedule a registered AQP agent |
| `agent:terminate` | Halt a running agent or revoke a long-lived spec |

### Trading / portfolio

| Scope | Description |
| --- | --- |
| `trade:read` | Inspect paper / live trading sessions, orders, fills, PnL |
| `trade:execute` | Submit paper-broker or sandbox-broker orders |
| `trade:live` | Submit real-money orders to a connected live broker |

### Backtesting

| Scope | Description |
| --- | --- |
| `backtest:read` | Inspect backtest runs and historical metrics |
| `backtest:create` | Submit a new backtest job to the engine fleet |

### ML / RL / RAG

| Scope | Description |
| --- | --- |
| `rag:query` | Query the hierarchical RAG corpus |
| `ml:workbench` | Run ML workbench flows (training, evaluation, registry) |
| `rl:train` | Submit `RLExperimentSpec` runs through `RLRuntime` |

### Deployment lifecycle

| Scope | Description |
| --- | --- |
| `deploy:run` | Run Terraform / Kubernetes deployments |
| `deploy:halt` | Halt AQP deployments and long-running runtimes |

### Terraform IaC (rule 42)

| Scope | Description |
| --- | --- |
| `terraform:plan` | Generate a Terraform plan for an AQP stack |
| `terraform:apply` | Apply a Terraform plan against an AQP stack |
| `terraform:destroy` | Destroy an AQP Terraform stack (super-admin only) |
| `terraform:cancel` | Cancel a running Terraform run |

### WorkloadRuntime (rule 45)

| Scope | Description |
| --- | --- |
| `workloads:halt` | Halt every running workload via the WorkloadRuntime kill-switch fan-out |

### Tenancy

| Scope | Description |
| --- | --- |
| `tenancy:invite` | Issue tenancy invites for org / team / workspace / project membership |
| `tenancy:admin` | Mutate tenancy state (orgs, teams, memberships) |
| `scim:write` | Provision AQP users and groups through SCIM |

### Platform

| Scope | Description |
| --- | --- |
| `platform:admin` | Implicit super-scope: satisfies any other scope check |

## Role lattice

Each role is a strict superset of the previous one (cumulative
composition). The lattice is enforced by the regression test at
`tests/auth/test_scopes.py::test_role_lattice_is_cumulative`.

### `aqp-viewer`

Read-only AQP operator for assigned resources.

- `read:infrastructure`
- `data:read`
- `agent:view`
- `trade:read`
- `backtest:read`
- `rag:query`

### `aqp-operator`

Viewer + manage assigned agents and bot workloads.

Adds:

- `manage:agents`
- `agent:execute`
- `agent:terminate`
- `backtest:create`
- `ml:workbench`
- `rl:train`
- `trade:execute`
- `deploy:run`
- `deploy:halt`
- `workloads:halt`

### `aqp-admin`

Operator + administrator for assigned organization infrastructure.

Adds:

- `manage:infrastructure`
- `data:write`
- `admin:iceberg`
- `terraform:plan`
- `terraform:apply`
- `terraform:cancel`
- `tenancy:invite`

### `aqp-superadmin`

Admin + cluster super-admin (the only role that bypasses
`aqp_platform_core.auth.resource_filter.filter_resources` via the
`admin:cluster` scope).

Adds:

- `admin:cluster`
- `terraform:destroy`
- `tenancy:admin`
- `scim:write`
- `trade:live`
- `platform:admin`

## Legacy tenancy roles

The tenancy database in `aqp.persistence.models_tenancy` uses a
separate role lattice (`viewer / editor / admin / owner`) for
membership in orgs, teams, workspaces, projects, and labs. The
canonical platform roles above (`aqp-*`) are issued by Auth0 and
expanded into scopes via the post-login Action sync. The translator
between the two lives at
[aqp/auth/scopes.py::legacy_role_to_aqp_role](../aqp/auth/scopes.py):

| Tenancy role | Canonical role |
| --- | --- |
| `viewer` | `aqp-viewer` |
| `editor` | `aqp-operator` |
| `admin` | `aqp-admin` |
| `owner` | `aqp-superadmin` |

The Auth0 sync endpoint (`/_internal/auth0/sync`) emits BOTH flavours
into the JWT's `roles` claim so legacy clients keep working AND scope
expansion produces a non-empty set. Closes the empty-claim drift bug
where a user whose only `Membership.role` was `editor` ended up with
no scopes in the token.

## Adding a new scope

1. Add the constant to `aqp/auth/scopes.py::AQPScope` and to
   `ALL_AQP_SCOPES`.
2. If the scope should be granted by a role, add it to the matching
   role frozenset in `aqp_platform_core/auth/rbac.py::_ROLE_LATTICE`
   (cumulative — viewer subset of operator subset of admin subset of
   superadmin).
3. Add the scope to `aqp_platform/terraform/modules/auth0_identity/main.tf`'s
   `local.scopes` AND to every role in `local.role_permissions` that
   should hold it.
4. Add a row to this catalogue (`aqp_docs/scopes.md`).
5. Re-run the regression test:
   `docker exec aqp-api python -m pytest tests/auth/test_scopes.py`.

The test asserts that the Python lattice and the Terraform lattice
contain the same scope set per role, so any drift produces a hard
failure rather than a silent grant.
