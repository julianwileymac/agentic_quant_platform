# AGENTS.md

Agent contract for `aqp_kernels`.

## Purpose

This boundary owns the AQP hybrid local↔cloud developer
experience: Jupyter Enterprise Gateway with a Kubernetes-aware
`KubernetesProcessProxy` ([`gateway/`](gateway/)), per-stack kernel
pod templates ([`pods/`](pods/)), the secret-broker sidecar that
exposes per-user Vault paths over a Unix domain socket
([`secret_broker/`](secret_broker/)), Dagster Pipes wrappers that
let local scripts target cloud execution
([`pipes/`](pipes/)), and the SDK auto-injection middleware that
makes `requests`/`httpx` calls from inside a kernel go through the
AQP rate-limit forward proxy
([`src/aqp_kernels/sdk_proxy.py`](src/aqp_kernels/sdk_proxy.py)).

The boundary also owns the matching Celery tasks
([`tasks/`](tasks/)), FastAPI routes ([`api/routes/`](api/routes/)),
configs ([`configs/`](configs/)), and tests ([`tests/`](tests/)).

## Hard Boundaries

1. **Every kernel pod is namespace-scoped to one user.** The
   Gateway provisions pods in `aqp-kernel-<uid>` namespaces,
   never a shared namespace. NetworkPolicies + ResourceQuotas
   isolate resource usage so one researcher can't squeeze
   another's GPU allocation.
2. **No vendor secrets touch the kernel pod's filesystem.** The
   secret-broker sidecar fetches per-user secrets from Vault at
   `secret/data/users/<uid>/services/<svc>` (the canonical path
   per [`aqp.credentials.vault_transit`](../aqp/credentials/vault_transit.py))
   and exposes them via a Unix domain socket the kernel reads at
   request time.
3. **All outbound vendor HTTP routes through the AQP rate-limit
   forward proxy** (root AGENTS.md rules 26 + 55). The
   kernel-startup hook in
   [`src/aqp_kernels/sdk_proxy.py`](src/aqp_kernels/sdk_proxy.py)
   sets `HTTPS_PROXY` AND monkey-patches `requests.Session` +
   `httpx.Client` so the per-(user, service, key_id) bucket
   debits even when the user imports those libraries AFTER
   kernel start.
4. **`kernel_sessions` is workspace-scoped + RLS-protected** per
   AGENTS rule 51 (Alembic 0074). New session ORM lifecycles
   route through [`aqp.persistence.models_kernels`](../aqp/persistence/models_kernels.py).
5. **Branch deployments carry sandboxed RLS budgets.** A PR
   ephemeral deployment gets a reservation against the parent
   branch's monthly quota, never the prod quota. The
   GitHub Action that drives `dagster-cloud
   branch-deployment create-or-update` reads the budget from
   `.github/aqp-budgets.yml`.

## Where Changes Go

- New kernel pod template: drop in [`pods/templates/`](pods/templates/)
  and reference from
  [`gateway/process_proxy.py`](gateway/process_proxy.py).
- New Pipes wrapper: extend [`pipes/`](pipes/) and re-export from
  [`src/aqp_kernels/pipes/__init__.py`](src/aqp_kernels/pipes/__init__.py).
- New CLI verb: extend [`src/aqp_kernels/cli/kernel_cmd.py`](src/aqp_kernels/cli/kernel_cmd.py).
- New REST surface: extend [`api/routes/kernels.py`](api/routes/kernels.py)
  and mount in the monolith's FastAPI app.
- Persistence model for `kernel_sessions` stays in the monolith
  ORM at [`../aqp/persistence/models_kernels.py`](../aqp/persistence/models_kernels.py)
  — this package depends on that row being there.

## Dependency rules

- This package depends on `aqp_ratelimit` for the
  `get_ratelimit_client` + `HTTPS_PROXY` chain.
- This package depends on the monolith for:
  `aqp.credentials.vault_transit` (Vault path scheme),
  `LedgerWriter`, `_progress.emit`. No reverse dependency
  (`aqp.*` MUST NOT import `aqp_kernels.*`).
- Optional: `jupyter-server`, `jupyter-enterprise-gateway`,
  `dagster-pipes` are all behind extras so the base install
  stays light.

## Validation

```bash
pip install -e .
pytest -ra
ruff check src tests
```
