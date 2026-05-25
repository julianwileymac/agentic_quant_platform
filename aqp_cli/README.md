# aqp-cli

Standalone operator CLI for the [Agentic Quant Platform](../README.md).

## Purpose

A single `aqp-cli` binary (`aqp` alias also supported) that:

1. **Streamlines local setup** — bootstrap `.env` files, verify prerequisites,
   create local volumes/networks, render derived configuration.
2. **Controls local runtimes** — start/stop/status/logs for the Vite client
   and local Theia IDE.
3. **Runs day-2 operations** — `cp`, `deploy`, and `viz` command groups for
   `/manage/*`, `/terraform/*`, `/visualizations/*`, and `/service-manager/*`.
4. **Authenticates + manages accounts** — `auth` and `account` command groups
   for `/auth/*` and `/me/*`.
5. **Unifies wrapper entrypoints** — `tools` and direct wrappers for
   `aqp-bots`, `aqp-control-plane`, `aqp-admin-api`, and helper scripts.

This binary is intentionally a thin client. All business logic lives in the
control plane, AQP API, and AQP runtimes. The CLI is an ergonomic surface
for operators.

## Boundaries

- Never imports `aqp.*` or `aqp_control_plane.*` source. Talks to them over
  HTTP only.
- Honors AQP rule 27 (no direct vendor SDK calls for identity — uses the
  control plane's `IdentityProvider` chain) and rule 26 (credentials
  resolve through the `CredentialResolver` chain on disk).
- Never prints raw tokens, kubeconfig contents, or secret payloads. Token
  output is redacted to a 4-character prefix per
  [.cursor/rules/aqp-management-engine.mdc](../.cursor/rules/aqp-management-engine.mdc).

## Install

```bash
pip install -e .[dev]            # base, no provider extras
pip install -e .[dev,docker]     # plus docker-py for compose probes
pip install -e .[dev,kubernetes] # plus kubernetes client for k8s probes
pip install -e .[dev,all-probes] # everything
```

## Usage

```bash
aqp-cli --help
aqp --help

# bootstrap (interactive)
aqp-cli setup init

# detect running services
aqp-cli services list
aqp-cli services status api

# local client + ide lifecycle
aqp-cli client start
aqp-cli client status
aqp-cli ide start
aqp-cli ide logs --lines 100

# deploy + control-plane operations
aqp-cli deploy up
aqp-cli cp deployments list
aqp-cli viz datasets
aqp-cli config get llm

# authenticate + account management
aqp-cli auth login --token "$AQP_ACCESS_TOKEN"
aqp-cli auth whoami
aqp-cli account profile
aqp-cli auth logout

# direct mode (emergency, requires --i-understand)
aqp-cli auth login --direct --i-understand
```

## Configuration

Read in priority order:

1. Environment variables prefixed with `AQP_CLI_*` (e.g.
   `AQP_CLI_API_URL`, `AQP_CLI_CONTROL_PLANE_URL`).
2. Cached auth/session state under `~/.config/aqp/credentials/` and
   process state under `~/.config/aqp/state/`.
3. Built-in defaults (`http://localhost:8000`, `http://localhost:9000`).

See [docs/index.md](docs/index.md) for the full operator runbook.

## Related

- [aqp_control_plane/](../aqp_control_plane/) — auth + `/manage/*` surface
- [aqp_docs/docs/concepts/identity/management-engine.md](../aqp_docs/docs/concepts/identity/management-engine.md) — runtime
  ops architecture
- [aqp_docs/docs/concepts/identity/identity.md](../aqp_docs/docs/concepts/identity/identity.md) — IdentityProvider contract
- [aqp_docs/docs/concepts/identity/credentials.md](../aqp_docs/docs/concepts/identity/credentials.md) — CredentialResolver
