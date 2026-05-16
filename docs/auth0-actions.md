# Auth0 Actions for the AQP multi-tenant rollout

The Phase 4 enforcement sweep relies on Auth0 to inject
AQP-namespaced custom claims (`https://aqp/org_id`,
`https://aqp/team_id`, `https://aqp/workspace_id`,
`https://aqp/roles`) into every access token. The Action snippet
below ships those claims by calling the M2M-secured
[`/_internal/auth0/sync`](../aqp/api/routes/auth0_sync.py)
endpoint during the post-login hook.

## Why an Action?

Auth0 ships organisation / role data via the standard `org_id` /
`https://<tenant>/roles` claims, but the **AQP scope chain**
(which workspace is the user's default, which team they're in,
which roles map onto the four-tier lattice) lives in Postgres.
The Action is the bridge: it asks the AQP backend on every login
+ injects the result into the access token so the frontend +
backend see a consistent set of custom claims from request 0.

## Setup

1. **Create an Auth0 API for the AQP backend** (separate from the
   SPA Application). Set the audience to whatever you set
   `AQP_AUTH_OIDC_AUDIENCE` to — e.g. `https://api.aqp.local`.
2. **Create a Machine-to-Machine Application** authorised against
   the AQP API. Set its allowed grant types to `client_credentials`
   only. Copy the client_id + secret into the Action's secrets:
   - `AQP_M2M_CLIENT_ID`
   - `AQP_M2M_CLIENT_SECRET`
   - `AQP_API_AUDIENCE` (the same audience as #1)
   - `AQP_BACKEND_URL` (e.g. `https://api.aqp.local`)
3. **Configure the AQP backend**:
   ```bash
   AQP_AUTH_PROVIDER=auth0
   AQP_AUTH_OIDC_ISSUER=https://your-tenant.auth0.com
   AQP_AUTH_OIDC_AUDIENCE=https://api.aqp.local
   AQP_AUTH_M2M_ENABLED=true
   AQP_AUTH_M2M_AUDIENCE=https://api.aqp.local
   AQP_AUTH_CLAIMS_NAMESPACE=https://aqp/
   AQP_AUTH_ENFORCE=permissive   # flip to ``strict`` after the rollout dashboard is clean
   ```

## The Action

Create a new Action under **Library > Custom > Build new** and
attach it to the **Login** trigger.

```js
/**
 * AQP post-login Action: lazy-provisions the internal user + injects
 * AQP-namespaced custom claims into the access token.
 *
 * Triggers on every login; the backend is idempotent.
 */
exports.onExecutePostLogin = async (event, api) => {
  const namespace = "https://aqp/";

  // 1. Mint an M2M token for the AQP backend.
  const tokenResp = await fetch(`https://${event.tenant.id}.auth0.com/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "client_credentials",
      client_id: event.secrets.AQP_M2M_CLIENT_ID,
      client_secret: event.secrets.AQP_M2M_CLIENT_SECRET,
      audience: event.secrets.AQP_API_AUDIENCE,
    }),
  });
  if (!tokenResp.ok) {
    api.access.deny("AQP backend token mint failed");
    return;
  }
  const { access_token } = await tokenResp.json();

  // 2. Ask the AQP backend to lazy-provision the user + return claims.
  const syncResp = await fetch(`${event.secrets.AQP_BACKEND_URL}/_internal/auth0/sync`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access_token}`,
    },
    body: JSON.stringify({
      user_id: event.user.user_id,
      email: event.user.email,
      organization_id: event.organization?.id,
      organization_name: event.organization?.name,
    }),
  });
  if (!syncResp.ok) {
    // Soft failure: let the user in but log the issue. The
    // backend's lazy provisioner will run on the first API call
    // instead.
    console.log("AQP backend sync failed:", await syncResp.text());
    return;
  }
  const claims = await syncResp.json();

  // 3. Inject the claims into the access token.
  if (claims.org_id) api.accessToken.setCustomClaim(`${namespace}org_id`, claims.org_id);
  if (claims.team_id) api.accessToken.setCustomClaim(`${namespace}team_id`, claims.team_id);
  if (claims.workspace_id) {
    api.accessToken.setCustomClaim(`${namespace}workspace_id`, claims.workspace_id);
  }
  if (claims.roles && claims.roles.length) {
    api.accessToken.setCustomClaim(`${namespace}roles`, claims.roles);
  }
  if (claims.internal_user_id) {
    api.accessToken.setCustomClaim(`${namespace}user_id`, claims.internal_user_id);
  }
};
```

## Verification

1. Log in via the SPA. The browser receives an access token.
2. Decode it (e.g. [jwt.io](https://jwt.io)) and verify the
   `https://aqp/org_id` / `https://aqp/roles` claims are present.
3. Hit `GET /auth/whoami` on the AQP backend. The response should
   reflect the org / workspace from the Action — not the
   deterministic local-default seed.
4. The Phase 6 frontend `ContextBar` should auto-populate the org
   / workspace on first render.

## Failure modes

| Symptom | Likely cause |
| ------- | ------------ |
| Token has no custom claims | Action attached to the wrong trigger or failed silently. Check the Action logs. |
| Backend 401 on `/_internal/auth0/sync` | M2M token audience mismatch — Action audience must equal `AQP_AUTH_OIDC_AUDIENCE`. |
| `data.ownership.list_resources` returns the local-default user | `provision_user_from_claims` is not running. Confirm the SPA is sending the Bearer header and `AQP_AUTH_PROVIDER != local`. |
| Phase 4 enforcement mode showing too many 403s | Some Postgres `memberships` rows are missing — run the lazy-provisioning sync once per user, or backfill manually. |

## See also

- [`docs/identity.md`](identity.md) — the full identity stack.
- [`docs/credentials.md`](credentials.md) — how M2M tokens flow
  through `CredentialResolver`.
- [`aqp/api/security.py`](../aqp/api/security.py) — the
  `require_scope` / `require_membership` deps that consume these
  claims.
