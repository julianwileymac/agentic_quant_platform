# `aqp_index/` debt note — Auth0 Refactor (Phases 1-8)

This commit touches every qualifying surface listed in
[.cursor/rules/aqp-index-reflect.mdc](../rules/aqp-index-reflect.mdc):

- [AGENTS.md](../../AGENTS.md): added Hard Rules 52-55; bumped "45 hard rules"
  reference to 55.
- [.cursor/rules/auth-stepup-and-byok.mdc](../rules/auth-stepup-and-byok.mdc):
  new always-on rule scoping the Phase 5+ files.
- [aqp_docs/auth0-setup.md](../../aqp_docs/auth0-setup.md): new
  comprehensive operator runbook.
- [aqp_docs/auth0-actions.md](../../aqp_docs/auth0-actions.md): extended with
  Phase 8 step-up MFA addendum, Phase 8 Custom Token Exchange Profile, and
  Phase 6 `aqp-idp-group-sync` Action.
- [.env.example](../../.env.example): new `AQP_AUTH_STEP_UP_*`,
  `AQP_AUTH0_LOG_STREAM_*`, `AQP_AUTH_AGENT_*` blocks.
- Public surface of multiple `aqp_*` boundary packages changed:
  - `aqp/auth/`: new `token_exchange.py`; extended `audit.py` signature
    (`on_behalf_of_user_id`, `agent_subject`, `delegation_profile`).
  - `aqp/api/`: new `security_stepup.py`; extended `security.py` with new
    `PUBLIC_ROUTERS` allowlist entries.
  - `aqp/api/routes/`: new `auth0_log_stream.py`, `broker_credentials.py`,
    `idp_connections.py`. Step-up MFA wired onto kill-switch + all 12
    halt routes + invites + oauth-connections delete + terraform
    apply/destroy + halt.
  - `aqp/persistence/`: new `models_broker.py`, `models_billing.py`;
    extended `models_tenancy.py` with `IdpConnectionRecord`,
    `IdpGroupMapping`, and the `broker_credential_backend` column on
    `Organization`.
  - `aqp/credentials/stores/`: new `broker_credential_store.py` at
    priority 4.
  - `aqp/tasks/`: new `session_revocation_tasks.py`.
  - `aqp/tenancy/strategies/hybrid.py`: extended with Redis pub/sub
    cache invalidation + `publish_strategy_changed` + subscriber.
  - `aqp/cache/keys.py`: new `broker_credentials` + `broker_providers`
    categories.
  - `aqp_cli/`: new `auth/device_flow.py` + `auth/keyring_store.py`;
    `commands/auth.py` adds `--device` subcommand, `diagnose` command.
    Pyproject adds `[keyring]` extra.
- New Alembic migration `alembic/versions/0065_broker_credentials_b2b.py`.

## Refresh checklist for the curator's next pass

The `aqp-index-curator` subagent should refresh the following
`aqp_index/` artefacts on its next scheduled run:

1. **Project surface map** — add `aqp/api/security_stepup.py`,
   `aqp/auth/token_exchange.py`, `aqp/api/routes/auth0_log_stream.py`,
   `aqp/api/routes/broker_credentials.py`,
   `aqp/api/routes/idp_connections.py`, `aqp/tasks/session_revocation_tasks.py`,
   `aqp/credentials/stores/broker_credential_store.py`,
   `aqp/persistence/models_broker.py`, `aqp/persistence/models_billing.py`,
   `aqp_cli/src/aqp_cli/auth/device_flow.py`,
   `aqp_cli/src/aqp_cli/auth/keyring_store.py` to the centralized index.

2. **Hard-rules table** — bump from 51 entries to 55 entries; cite
   the new rule numbers + canonical implementation files.

3. **Configuration registry** — add the seven new `AQP_AUTH_STEP_UP_*` /
   `AQP_AUTH0_LOG_STREAM_*` / `AQP_AUTH_AGENT_*` settings to the
   consolidated config index with their defaults + rollout notes.

4. **Code indices** — refresh the per-package code index for
   `aqp/api/`, `aqp/auth/`, `aqp/credentials/`, `aqp/persistence/`,
   `aqp/tenancy/`, `aqp_cli/`, and `aqp_client/` with the new
   public-surface entries.

5. **Skills + subagent registries** — no new skills or subagents
   were introduced; the existing `aqp-management-engine` subagent's
   credential-safety rule covers the new modules transparently.

## Verification

Once the curator refresh lands, this debt note can be deleted. Until
then, this file documents WHY the index temporarily lags reality.
