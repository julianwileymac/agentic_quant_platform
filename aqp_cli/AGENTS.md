# AGENTS.md

Agent contract for `aqp_cli`.

## Purpose

This is a **thin operator CLI** that talks to AQP services over HTTP. It is
NOT a place to put new business logic. Every command resolves into:

- a call to `/manage/*` on `aqp_control_plane` (preferred), OR
- a call to `/auth/*` / `/data/*` on the AQP monolith, OR
- a local probe (Docker socket, kubernetes context, filesystem) when
  no remote endpoint can answer the question.

## Hard Boundaries

1. **Never import `aqp.*` or `aqp_control_plane.*` source.** This CLI ships
   independently and must run against a remote AQP install.
2. **All identity flows go through `IdentityProvider`** on the control
   plane (AQP rule 27). The `--direct` flag is a documented escape hatch
   that requires an explicit `--i-understand` acknowledgement.
3. **Credentials resolve through `CredentialResolver`** (AQP rule 26).
   On-disk storage lives under `~/.config/aqp/credentials/`.
4. **Never print raw tokens, kubeconfig contents, or secret payloads.**
   Token output is redacted to a 4-character prefix; secret values are
   replaced with `<redacted>`. See
   [.cursor/rules/aqp-management-engine.mdc](../.cursor/rules/aqp-management-engine.mdc).
5. **Service URLs resolve via the topology service**, not via hard-coded
   constants. The CLI calls `GET /manage/topology/*` (or
   `GET /control-plane/topology` on the monolith) and caches the result
   to `~/.config/aqp/topology.json`.

## Where Changes Go

- New `aqp-cli <subcommand>`: `src/aqp_cli/commands/<subcommand>.py`,
  registered into [src/aqp_cli/cli.py](src/aqp_cli/cli.py).
- New backend HTTP client wrapper: `src/aqp_cli/clients/`.
- Output helpers (rich tables, JSON renderers): `src/aqp_cli/ui/`.
- Settings field: `src/aqp_cli/config.py` (prefix `AQP_CLI_*`).
- Tests: `tests/` (use `respx` for httpx mocking).

## Validation

```bash
pip install -e .[dev]
pytest -ra
ruff check src tests
mypy src
```

Required CI guard (mirrors `aqp_control_plane`):

```bash
# Must return no matches — the CLI cannot import AQP server code directly.
rg --type py "^from (aqp|aqp_cp|aqp_control_plane)(\\.|$)|^import (aqp|aqp_cp|aqp_control_plane)(\\.|$)" src
```
