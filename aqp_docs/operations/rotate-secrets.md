# Operations runbook — Secret rotation

Zero-downtime credential rotation for the AQP control plane + workloads.

## What's a secret here?

Every entry in [`aqp_platform/deployments/compose/.env.schema`](../../aqp_platform/deployments/compose/.env.schema) with `classification: secret` or `classification: rotation-required`. The rotation-required ones (e.g. `AUTH0_M2M_CLIENT_SECRET`) should be rotated on a fixed schedule (typically 90 days).

## Pre-flight

1. Confirm at least one operator with `admin:cluster` is online to handle Auth0 console operations.
2. Check `kubectl -n aqp rollout status deployment/aqp-core` — if it's currently degraded, fix that first.
3. Verify the secret store you're rotating into is reachable (`Vault sealed?`, `SSM blocked by SCP?`, etc.).

## Procedure — Auth0 M2M client secret

1. **Mint a new secret in Auth0:** Applications → `aqp-m2m` → Settings → "Rotate" (Auth0 keeps the old one valid for 24h by default).
2. **Update the secret store:**

   ```powershell
   # Vault example
   vault kv patch secret/aqp/auth0 m2m_client_secret=<new-value>
   ```

3. **Reload the relevant pods:**

   ```powershell
   kubectl -n aqp rollout restart deployment/aqp-core
   kubectl -n aqp rollout restart deployment/aqp-worker
   kubectl -n aqp-admin rollout restart deployment/aqp-cp
   ```

4. **Verify:** `curl https://manage.aqp.enterprise.com/manage/health` returns 200; the audit log shows successful M2M token mints.
5. **Revoke the old secret:** Auth0 → `aqp-m2m` → "Revoke previous secret" once you're confident every pod has rolled.

## Procedure — Postgres password

1. **Connect via the old credential** and create the new password:

   ```sql
   ALTER USER aqp WITH PASSWORD 'new-strong-password';
   ```

2. **Update the secret store** (same as above).
3. **Rolling restart** of every service that talks to Postgres: `aqp-core`, `aqp-worker`, `aqp-cp`. Each pod re-reads the env var on startup.
4. **No old-credential revocation needed** — Postgres only honours the current password.

## Procedure — Session cookie secret

The session cookie secret (`AQP_SESSION_COOKIE_SECRET`) is used to encrypt the `aqp_session` cookie. Rotating it invalidates every active session.

1. Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
2. Update the secret store.
3. Rolling restart of `aqp-core` only. Users will be redirected to Auth0 to re-authenticate.

## Procedure — SCIM bearer token

The SCIM bearer token hash gates the `/scim/v2/*` endpoint.

1. Generate a new random token: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Compute its SHA-256 hash: `python -c "import hashlib, sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" <new-token>`
3. Update `AQP_AUTH_SCIM_BEARER_TOKEN_HASH` in the secret store with the hash.
4. Update the IdP's SCIM provisioning configuration with the new RAW token.
5. Rolling restart of `aqp-core`.

## Auditing

Every secret rotation should leave a trace:

- The secret store records the change (Vault audit log / Cloudtrail / Cloud Audit Logs)
- The application's audit log shows the M2M / Postgres / cookie events
- `aqp_control_plane`'s `WorkloadRun` ledger records the rotation request

If you can't see all three, file an incident — silent rotations are a security smell.
