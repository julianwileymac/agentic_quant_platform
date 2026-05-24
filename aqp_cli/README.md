# aqp-cli

Standalone operator CLI for the [Agentic Quant Platform](../README.md).

## Purpose

A single `aqp-cli` binary that:

1. **Streamlines local setup** — bootstrap `.env` files, verify prerequisites,
   create local volumes/networks, render derived configuration.
2. **Detects running services** — surface the live state of the AQP stack
   (Docker Compose, local Kubernetes/k3d, in-process services), highlighting
   discrepancies between configured topology and what is actually running.
3. **Fetches updates** — pull repo updates, pin component versions, run the
   right migration / restart steps.
4. **Authenticates** — primary path is brokered through the control plane
   (`/auth/*` on `aqp_control_plane`), with an opt-in `--direct` mode for
   emergency direct-to-Auth0/OIDC.

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

# bootstrap (interactive)
aqp-cli setup init

# detect running services
aqp-cli services list
aqp-cli services status

# pull updates
aqp-cli update check
aqp-cli update apply

# authenticate (control plane brokered)
aqp-cli auth login
aqp-cli auth whoami
aqp-cli auth logout

# direct mode (emergency, requires --i-understand)
aqp-cli auth login --direct --i-understand
```

## Configuration

Read in priority order:

1. CLI flags (`--api-url`, `--control-plane-url`, ...).
2. Environment variables prefixed with `AQP_CLI_*` (e.g.
   `AQP_CLI_API_URL`, `AQP_CLI_CONTROL_PLANE_URL`).
3. User config file at `~/.config/aqp/cli.toml`.
4. Defaults (resolve via the topology service when reachable).

See [docs/index.md](docs/index.md) for the full operator runbook.

## Related

- [aqp_control_plane/](../aqp_control_plane/) — auth + `/manage/*` surface
- [aqp_docs/management-engine.md](../aqp_docs/management-engine.md) — runtime
  ops architecture
- [aqp_docs/identity.md](../aqp_docs/identity.md) — IdentityProvider contract
- [aqp_docs/credentials.md](../aqp_docs/credentials.md) — CredentialResolver
