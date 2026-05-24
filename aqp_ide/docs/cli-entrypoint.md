# AQP IDE CLI entrypoint (`aqp-cli ide`)

`aqp-cli ide` is the **canonical entrypoint** for the AQP Theia IDE.
Direct `yarn` invocations are inner-loop development only; every
production / Docker / Kubernetes workflow goes through this CLI.

## Subcommand map

| Subcommand | Purpose | Backing actions |
| --- | --- | --- |
| `install [--frozen-lockfile]` | One-time `yarn install` in `aqp_ide/` | local yarn |
| `build [--dev/--prod]` | `yarn build:extensions` + `yarn build:applications[:dev]` | local yarn |
| `start [--background/--foreground] [--port N] [--workspace P] [--open]` | Spawn Theia; persist `pid` + `port` to state file | local yarn |
| `stop` | Kill the backgrounded Theia process | `SIGTERM` / `taskkill` |
| `status` | Running pid, log path, port, URL | local read |
| `logs [--lines N]` | Tail `ide.log` | local read |
| `open [--no-browser]` | Open the IDE URL in the default browser | `webbrowser.open` |
| `url [--remote]` | Print local URL OR (with `--remote`) the cluster URL via topology | local OR `/manage/topology/services` |
| `env [--write PATH]` | Render the recommended `AQP_THEIA_*` env block | local + best-effort `/manage/topology/services` |
| `detect` | Surface every reachable Theia (local + cluster) | local probe + `/manage/topology/services` |
| `doctor` | Preflight checks: yarn / port / lockfile / auth / running pid | local + keyring |

## First-run sequence

```bash
# 1. Authenticate (RFC 8628 device flow, OS keyring)
aqp-cli auth login --device

# 2. Bootstrap node modules in aqp_ide/ (one-time)
aqp-cli ide install

# 3. Build the bundles (~2-3 minutes after first install)
aqp-cli ide build --dev

# 4. Spawn Theia + open in browser
aqp-cli ide start --open

# 5. When done:
aqp-cli ide stop
```

## Day-to-day operations

```bash
# Where is the IDE running, and on which port?
aqp-cli ide status

# Tail logs for the last 500 lines
aqp-cli ide logs --lines 500

# Bring up a Theia on port 3030 and pin a workspace
aqp-cli ide start --port 3030 --workspace ~/work/strategy-research --open

# Print just the URL (handy for piping into scripts)
aqp-cli ide url

# Print the cluster-side URL via the AQP topology service
aqp-cli ide url --remote

# Render the recommended env block; pipe to a file for Docker / K8s
aqp-cli ide env --write ./.env.theia

# Show every reachable Theia instance (local AND cluster)
aqp-cli ide detect

# Pre-flight checks before reporting a bug
aqp-cli ide doctor
```

## Settings (env-overridable)

All settings are prefixed `AQP_CLI_*` per `aqp-cli.mdc`:

| Setting | Default | Override env var |
| --- | --- | --- |
| `theia_port` | `3000` | `AQP_CLI_THEIA_PORT` |
| `theia_url` | `http://localhost:3000` | `AQP_CLI_THEIA_URL` |
| `theia_workspace` | (empty) | `AQP_CLI_THEIA_WORKSPACE` |
| `theia_yarn_offline` | `false` | `AQP_CLI_THEIA_YARN_OFFLINE` |
| `theia_docker_image` | `aqp/aqp-ide:dev` | `AQP_CLI_THEIA_DOCKER_IMAGE` |

State files (created automatically by `ensure_state_dirs`):

- `~/.config/aqp/state/ide-process.json` — pid, port, command, started_at
- `~/.config/aqp/state/ide.log` — tailed by `logs`
- `~/.config/aqp/credentials/auth-session.json` — legacy fallback
- OS keyring — primary token store (rule 53)

## Hard-rule contract

- **HTTP-only.** Every subcommand resolves to local yarn, an HTTP call,
  or a local probe. No `aqp.*` / `aqp_control_plane.*` source imports.
- **Identity.** `auth login --device` (RFC 8628), tokens persisted via
  `KeyringStore` (rule 53). Token output is redacted to a 4-character
  prefix per `.cursor/rules/aqp-management-engine.mdc`.
- **Topology.** `detect` / `url --remote` / `env` consult
  `GET /manage/topology/services` (rule 47) before falling back to
  local probes.

## Failure modes + diagnostics

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `yarn not on PATH` | yarn 1.x not installed | Install yarn classic (Theia 1.72 requires yarn 1) |
| `port 3000 is in use` | Another process is bound | Pick a different port: `aqp-cli ide start --port 3030` |
| `auth token present: MISSING` | Never signed in | `aqp-cli auth login --device` |
| `aqp_ide/yarn.lock: MISSING` | First run | `aqp-cli ide install` |
| `local Theia running: stopped` after start | Crash during boot | `aqp-cli ide logs --lines 200` |
| MCP servers don't show up | Missing env vars | `aqp-cli ide env` then update Docker / K8s config |

## See also

- [../../aqp_cli/docs/index.md](../../aqp_cli/docs/index.md) — full CLI doc
- [deployment.md](deployment.md) — Docker / K8s / Theia Cloud
- [extensions.md](extensions.md) — what runs inside the IDE
