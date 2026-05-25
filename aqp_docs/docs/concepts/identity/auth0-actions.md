---
title: 'Auth0 Actions for the AQP multi-tenant rollout'
summary: 'Auth0 ships organisation / role data via the standard `org_id` / `https://<tenant>/roles` claims, but the **AQP scope chain** (which workspace is the users default, which team theyre in, which roles...'
owner: identity-team
last_reviewed: 2026-05-25
audience: both
---

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

- [`aqp_docs/identity.md`](../../concepts/identity/identity.md) — the full identity stack.
- [`aqp_docs/credentials.md`](../../concepts/identity/credentials.md) — how M2M tokens flow
  through `CredentialResolver`.
- [`aqp/api/security.py`](../aqp/api/security.py) — the
  `require_scope` / `require_membership` deps that consume these
  claims.

## Phase 7 post-login Action (Auth0 + Microsoft federation)

This Action calls `/_internal/auth0/sync`, then injects returned custom
claims into both the access token and ID token. The connection name
mapping (`requested_claims.connection`) is forwarded so AQP can record
which IdP drove each login.

```javascript
/**
 * AQP post-login Action.
 * Calls /_internal/auth0/sync on the AQP API and injects the
 * returned custom claims into the access token. Also carries the
 * Auth0 connection name (e.g. "azure-ad-myorg") so the AQP audit
 * log records WHICH IdP drove this login.
 *
 * Secrets used:
 *   AQP_API_URL                  e.g. https://api.aqp.example
 *   AQP_M2M_CLIENT_ID            Auth0 Management API M2M client id (reused)
 *   AQP_M2M_CLIENT_SECRET        Auth0 Management API M2M client secret
 *   AQP_M2M_AUDIENCE             Same as AQP API resource identifier
 *
 * Set them at: Actions > Library > Custom > <your action> > Add Secret
 */
const NS = "https://aqp/";

async function mintM2MToken(secrets) {
  const url = `https://${event.tenant.id}.auth0.com/oauth/token`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      grant_type: "client_credentials",
      client_id: secrets.AQP_M2M_CLIENT_ID,
      client_secret: secrets.AQP_M2M_CLIENT_SECRET,
      audience: secrets.AQP_M2M_AUDIENCE,
    }),
  });
  if (!res.ok) return null;
  const body = await res.json();
  return body.access_token || null;
}

exports.onExecutePostLogin = async (event, api) => {
  const aqpApi = event.secrets.AQP_API_URL;
  if (!aqpApi) return; // Action mis-configured; fail open
  let token = await api.cache.get("aqp_m2m_token");
  if (!token || !token.value) {
    const fresh = await mintM2MToken(event.secrets);
    if (!fresh) return;
    api.cache.set("aqp_m2m_token", fresh, { ttl: 50 * 60 * 1000 });
    token = { value: fresh };
  }
  const payload = {
    user_id: event.user.user_id,
    email: event.user.email,
    organization_id: event.organization?.id,
    organization_name: event.organization?.name,
    requested_claims: {
      connection: event.connection?.name,
      strategy: event.connection?.strategy,
    },
  };
  try {
    const res = await fetch(`${aqpApi}/_internal/auth0/sync`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token.value}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return;
    const claims = await res.json();
    for (const [k, v] of Object.entries(claims)) {
      if (v === null || v === undefined) continue;
      api.accessToken.setCustomClaim(`${NS}${k}`, v);
      api.idToken.setCustomClaim(`${NS}${k}`, v);
    }
  } catch (err) {
    // Fail open — never block the user's login if AQP API is down.
    console.log("aqp_sync_failed", err.message);
  }
};
```

### Custom claims it sets

| Claim | Meaning |
| --- | --- |
| `https://aqp/org_id` | Active organization context resolved by AQP. |
| `https://aqp/team_id` | Team context resolved by AQP. |
| `https://aqp/workspace_id` | Active workspace context. |
| `https://aqp/project_id` | Active project context. |
| `https://aqp/lab_id` | Active lab context. |
| `https://aqp/roles` | Role list used by scope/membership checks. |
| `https://aqp/connection` | Auth0 connection name, mapped from `requested_claims.connection` (for example `azure-ad-myorg`). |
| `https://aqp/internal_user_id` | AQP internal user row identifier. |

### Why it fails open

The post-login Action should never block authentication because of a
transient outage in AQP. Missing one claim-sync cycle is recoverable on
the next login, while hard-failing login creates a broader availability
incident for all users.

## Phase 8 — Step-up MFA addendum (AGENTS hard rule 52)

Step-up MFA on destructive routes (the kill switch, every `/halt`
endpoint, BYOK / OAuth credential deletes, Terraform apply / destroy,
organization invite issuance, broker-credential mutations, and the
admin tenancy-strategy migration) is enforced server-side by
[`aqp.api.security_stepup.require_step_up`](../aqp/api/security_stepup.py).
The FastAPI dep returns RFC 9470-compliant 401 responses with
`WWW-Authenticate: Bearer error="insufficient_user_authentication",
acr_values="...", max_age="..."` when the access token fails the
freshness or MFA-method check.

The frontend (`aqp_client/src/lib/auth/useStepUp.ts` +
`apiFetch` retry middleware) drives the SPA-side flow: a destructive
button calls `requestStepUp()` to pre-flight an Auth0 popup with
`acr_values=http://schemas.openid.net/pape/policies/2007/06/multi-factor`
and `max_age=0`, then runs the original operation with the freshly
minted token. For this round-trip to succeed, the post-login Action
above MUST honour the `acr_values` parameter and force an MFA
challenge when the caller requested it.

Add the snippet below to the **Phase 7 post-login Action** (don't
duplicate — extend the existing `exports.onExecutePostLogin`):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  // ... (the Phase 7 JIT-sync body stays as-is) ...

  // ---- Phase 8: Adaptive MFA + step-up enforcement ------------------

  // The SPA / CLI / agent caller can explicitly request fresh MFA by
  // passing acr_values=http://schemas.openid.net/pape/policies/2007/06/multi-factor
  // on /authorize. The Action MUST trigger the MFA challenge when
  // either (a) the caller requested it OR (b) Auth0's Adaptive MFA
  // assessment flagged the login as high-risk.
  const ACR_MFA = "http://schemas.openid.net/pape/policies/2007/06/multi-factor";
  const acrRequested = Array.isArray(event.transaction?.acr_values)
    ? event.transaction.acr_values
    : [];
  const explicitlyAskedForMfa = acrRequested.includes(ACR_MFA);

  const methods = Array.isArray(event.authentication?.methods)
    ? event.authentication.methods
    : [];
  const mfaAlreadyCompleted = methods.some(
    (m) => m?.name === "mfa" || m?.name === "otp",
  );

  // Auth0's Adaptive MFA risk assessment — `low` / `medium` / `high`.
  // Honour `high` automatically; `medium` is left to the caller's
  // explicit request so the dashboard stays usable on shared offices.
  const riskConfidence = event.authentication?.riskAssessment?.confidence;

  const shouldTriggerMfa =
    (explicitlyAskedForMfa && !mfaAlreadyCompleted) ||
    riskConfidence === "high";

  if (shouldTriggerMfa) {
    // ``allowRememberBrowser: false`` because step-up is sized for
    // destructive ops — we never want the browser to remember the
    // "MFA satisfied" flag past the 180s freshness window.
    api.multifactor.enable("any", { allowRememberBrowser: false });
  }

  // Surface a JIT-friendly hint to the SPA so the topbar can render
  // "MFA required" pre-flight UI. Not security-sensitive — purely a
  // UX accelerator. The backend NEVER trusts this claim; it always
  // re-checks amr + auth_time on the access token.
  api.idToken.setCustomClaim(`${NS}mfa_available`, true);
};
```

The `multifactor.enable("any", ...)` call triggers Auth0's enrolment
or challenge surface, depending on whether the user has already
registered a factor. Operators must enable at least one factor type
in **Security > Multi-factor Auth** for the call to succeed.

### Tested factor types

| Factor | Auth0 enrolment | Notes |
| --- | --- | --- |
| OTP (TOTP) | Authenticator app | Always recommended as the primary factor |
| WebAuthn | Roaming or Platform | Strongest; emits `amr: ["mfa", "swk"]` or `["mfa", "hwk"]` |
| Push | Auth0 Guardian app | Smooth UX for personal accounts |
| SMS | Phone-based | Discouraged for B2B per AGENTS rule 52 |
| Email OTP | Magic link | Acceptable; emits `amr: ["mfa"]` |
| Recovery code | Backup | Always provisioned alongside another factor |

### Step-up failure recovery

If the popup fails (browser blocked, user dismissed, network drop):

- `useStepUp.requestStepUp()` returns `null` and surfaces a "MFA
  required" toast.
- `apiFetch`'s automatic 401 retry path also surrenders after one
  attempt; the route handler propagates the original 401 to the
  caller.
- Operators with `admin:tenant` can fall back to the BFF
  `/auth/login?acr_values=...` redirect flow which uses a full-page
  redirect instead of a popup. The redirect callback returns to the
  original route and the user re-clicks the destructive button.

## Phase 8 — Custom Token Exchange Profile (AGENTS hard rule 54)

The Phase 8 refactor introduces RFC 8693 delegated agent tokens —
when [`AgentRuntime`](../aqp/agents/runtime.py) makes an HTTP MCP
call on behalf of a user, it exchanges the user's access token for a
narrower, agent-scoped token via Auth0 Custom Token Exchange. The
minted token carries an `act` claim identifying the agent, while the
top-level `sub` stays the human user — so RLS, memberships, and the
audit ledger all see the full delegation chain.

### Required Auth0 setup

1. **Create an M2M Application named `aqp-agent-broker`.**
   - Authorise it against the AQP API record.
   - Allowed grant types: `client_credentials` (required) AND
     `urn:ietf:params:oauth:grant-type:token-exchange` (required).
   - Note the `client_id` + `client_secret`.

2. **Configure backend env vars:**

   ```bash
   AQP_AUTH_AGENT_TOKEN_EXCHANGE_ENABLED=true
   AQP_AUTH_AGENT_BROKER_CLIENT_ID=<aqp-agent-broker client_id>
   # client_secret resolves via CredentialResolver in prod
   # (Vault / cloud KMS) — env is the local-dev shortcut:
   AQP_AUTH_AGENT_BROKER_CLIENT_SECRET=<aqp-agent-broker client_secret>
   AQP_AUTH_AGENT_DELEGATION_TTL_SECONDS=300
   ```

3. **Create a Custom Token Exchange Profile named `aqp-agent-delegation`.**
   - In the Auth0 Dashboard, navigate to **Actions > Flows > Custom Token
     Exchange** and click "Create Profile".
   - Profile name: exactly `aqp-agent-delegation` (matches the
     `subject_token_profile` parameter the broker sends).
   - Target API: the AQP API record (audience
     `https://api.aqp.fund/` or your env equivalent).
   - Subject token types accepted:
     `urn:ietf:params:oauth:token-type:access_token`.
   - Allow Skipping User Consent: **enabled** (required for
     non-interactive flows per the Custom Token Exchange docs).
   - Allowed scopes: `read:mcp:data`, `write:mcp:data`,
     `read:mcp:codebase`, `write:mcp:codebase`. The Profile must
     reject any scope NOT on this list.

### The Action body

Paste this into the Profile's Action body. The Action runs INSIDE
the `/oauth/token` exchange request — it never returns prose to the
caller, only the access token Auth0 mints.

```javascript
/**
 * aqp-agent-delegation — Custom Token Exchange Profile Action.
 *
 * Sources:
 *   event.transaction.subject_token_payload — the human's verified
 *     access token claims (sub, org_id, permissions, ...).
 *   event.transaction.actor_token_payload   — the agent broker M2M
 *     token claims (sub = "agent|<spec_name>").
 *
 * The Profile MUST be paired with the aqp-agent-broker M2M client
 * and the broker MUST NOT be allowed to call /oauth/token with any
 * other Profile. Misusing this Profile mis-attributes audit rows.
 */
exports.onExecuteCustomTokenExchange = async (event, api) => {
  const subject = event.transaction?.subject_token_payload;
  const actor = event.transaction?.actor_token_payload;

  if (!subject || typeof subject !== "object") {
    api.access.rejectInvalidSubjectToken("subject token missing");
    return;
  }
  if (!actor || typeof actor !== "object") {
    api.access.rejectInvalidSubjectToken("actor assertion missing");
    return;
  }

  const humanSub = subject.sub;
  const agentSub = actor.sub;
  if (!humanSub || !agentSub) {
    api.access.rejectInvalidSubjectToken("missing sub claims");
    return;
  }
  if (!String(agentSub).startsWith("agent|")) {
    api.access.rejectInvalidSubjectToken(
      "actor must identify an agent (sub must start with 'agent|')",
    );
    return;
  }

  // Bind the minted access token to the human user — RLS + members
  // are evaluated against this sub by the AQP backend.
  api.authentication.setUserById(humanSub);

  // Narrow audience + scopes regardless of what the subject token had.
  api.accessToken.setAudience(event.secrets.AQP_API_AUDIENCE);

  // Whitelist of scopes the agent is allowed to inherit. New MCP
  // surfaces must be added to BOTH this list AND the Profile's
  // configured allowed scopes.
  const ALLOWED_AGENT_SCOPES = [
    "read:mcp:data",
    "write:mcp:data",
    "read:mcp:codebase",
    "write:mcp:codebase",
  ];
  const requested = (event.transaction?.requested_scopes || []).filter(
    (s) => ALLOWED_AGENT_SCOPES.includes(s),
  );
  for (const s of requested) {
    api.accessToken.addScope(s);
  }

  // The `act` claim is the standard RFC 8693 marker. AQP's
  // get_current_user dep reads it to flip Principal.actor_type to
  // "agent" and stamp on_behalf_of_sub onto every audit row.
  api.accessToken.setCustomClaim("act", {
    sub: agentSub,
    iss: `https://${event.secrets.AUTH0_DOMAIN}/`,
  });

  // AQP-specific marker so the frontend / SIEM dashboards can filter.
  api.accessToken.setCustomClaim("aqp_delegated", true);

  // Carry the human's org_id through so RLS sees the right tenant
  // even when the agent is running in a Celery worker without
  // X-AQP-Org headers.
  if (subject.org_id) {
    api.accessToken.setCustomClaim("org_id", subject.org_id);
  }
};
```

### Secrets

- `AQP_API_AUDIENCE` — same value the operator sets in
  `AQP_AUTH_OIDC_AUDIENCE` on the backend.
- `AUTH0_DOMAIN` — the tenant domain
  (`aqp-prod.us.auth0.com` or the custom domain).

### Verification

1. Stand the backend up with `AQP_AUTH_AGENT_TOKEN_EXCHANGE_ENABLED=true`
   and the broker credentials populated.
2. Run an end-to-end test where an agent calls a data MCP tool:

   ```python
   from aqp.agents.runtime import AgentRuntime
   from aqp.agents.spec import AgentSpec

   spec = AgentSpec.from_yaml_path("configs/agents/research_lead.yaml")
   runtime = AgentRuntime(
       spec,
       context=test_ctx,
       user_access_token=human_token,
   )
   delegated = runtime.delegated_token_for_mcp()
   assert delegated is not None
   # Decode the token at jwt.io — should carry act.sub="agent|research_lead"
   # while sub stays the human's auth0|... identity.
   ```

3. Hit `/mcp/data/tools/data.catalog.lineage/invoke` with the
   delegated token in the `Authorization` header. The response body
   should include the `actor` object with both the agent sub and the
   on-behalf-of sub.

4. Query the audit ledger:

   ```sql
   SELECT created_at, user_id, actor_user_id, event_type,
          details->'delegation' AS delegation
   FROM security_audit_events
   WHERE event_type LIKE 'mcp%'
   ORDER BY created_at DESC LIMIT 5;
   ```

   The `delegation` JSON block should carry
   `{"agent_subject": "agent|research_lead", "on_behalf_of_user_id":
   "auth0|...", "profile": "aqp-agent-delegation"}`.

### Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| 400 `invalid_request profile not found` | Profile name typo or not yet created in Dashboard | Match the name exactly: `aqp-agent-delegation` |
| 400 `unauthorized_client` | aqp-agent-broker app missing `token-exchange` grant type | Enable on the M2M app |
| 400 `invalid_target scope rejected` | Profile didn't include the scope in its allowed list | Add the scope to BOTH the Profile config and the Action's `ALLOWED_AGENT_SCOPES` list |
| MCP route returns 403 missing `read:mcp:data` | Permissions array on AQP API record missing the scope, or RBAC option "Add permissions in access token" is off | Re-enable both in API record settings |
| Audit row missing `delegation` block | Caller didn't pass `agent_subject` to `emit_audit_event` | The MCP server route + bridge already pass it; legacy callers need to be updated |

## Phase 6 — IdP group sync Action (`aqp-idp-group-sync`)

Generalises the existing post-login flow so each org can attach
non-Entra IdPs (Google Workspace, AWS IAM Identity Center, Okta,
OneLogin, JumpCloud, generic SAML/OIDC) and have their external
group claims automatically promote to AQP roles. Pairs with the
[`IdpGroupMappingEditor`](../aqp_client/src/components/onboarding/IdpGroupMappingEditor.tsx)
admin UI and the `/tenancy/orgs/{org_id}/idp-group-mappings`
routes.

### How it fits the post-login pipeline

The existing `aqp-post-login` Action handles the JIT user upsert
and the AQP-namespaced custom claims (Phase 4 + 7). This NEW
Action runs AFTER `aqp-post-login` in the same Login trigger and
specifically handles the IdP-group → AQP-role translation. They
share the M2M token cache to avoid double-minting.

### Required Auth0 setup

1. **Order the Actions.** In Library > Custom > Triggers > Login,
   drag `aqp-post-login` to position 1, then `aqp-idp-group-sync`
   to position 2. The sync action depends on `event.user.user_id`
   being a valid AQP user, which is guaranteed by the time the
   post-login JIT sync completes.

2. **No new secrets** — re-uses the same `AQP_API_URL` /
   `AQP_M2M_*` secrets the post-login Action already needs.

### The Action body

```javascript
/**
 * aqp-idp-group-sync — post-login Action.
 *
 * Reads the user's external IdP group claims and posts them to
 * /_internal/idp/sync-groups so the AQP backend can upsert
 * matching Membership rows per the per-org IdpGroupMapping table.
 */
const NS = "https://aqp.internal/";

function _collectExternalGroups(event) {
  // Different IdPs surface group memberships under different claim
  // names. We collect every well-known shape and merge into one
  // de-duplicated list.
  const candidates = [
    event.user?.groups,          // Auth0 standard
    event.user?.app_metadata?.groups,
    event.user?.user_metadata?.groups,
    event.user?.["http://schemas.microsoft.com/ws/2008/06/identity/claims/role"],
    event.user?.identities?.[0]?.profileData?.groups,
  ];
  const merged = new Set();
  for (const c of candidates) {
    if (!c) continue;
    if (Array.isArray(c)) {
      for (const g of c) {
        if (typeof g === "string" && g.trim()) merged.add(g.trim());
      }
    } else if (typeof c === "string" && c.trim()) {
      merged.add(c.trim());
    }
  }
  return Array.from(merged);
}

function _connectionKind(event) {
  // Map Auth0 connection strategy -> AQP IdpConnectionRecord.connection_kind.
  const strategy = (event.connection?.strategy || "").toLowerCase();
  const name = (event.connection?.name || "").toLowerCase();
  if (strategy === "waad" || name.includes("azure")) return "entra";
  if (strategy === "google-workspace" || name.includes("google-workspace")) {
    return "google_workspace";
  }
  if (name.includes("iam-identity-center") || name.includes("aws-sso")) {
    return "aws_iam_identity_center";
  }
  if (strategy === "okta" || name.includes("okta")) return "okta";
  if (strategy === "onelogin" || name.includes("onelogin")) return "onelogin";
  if (strategy === "jumpcloud" || name.includes("jumpcloud")) return "jumpcloud";
  if (strategy === "samlp") return "generic_saml";
  if (strategy === "oidc") return "generic_oidc";
  return null;
}

exports.onExecutePostLogin = async (event, api) => {
  const groups = _collectExternalGroups(event);
  if (groups.length === 0) return;
  const kind = _connectionKind(event);
  if (!kind) return;

  // Re-use the M2M token cached by aqp-post-login (same Action
  // namespace) so we don't double-mint.
  const token = (await api.cache.get("aqp_m2m_token"))?.value;
  if (!token) return;

  const aqpApi = event.secrets.AQP_API_URL;
  if (!aqpApi) return;

  try {
    await fetch(`${aqpApi}/_internal/idp/sync-groups`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        user_id: event.user.user_id,
        auth0_organization_id: event.organization?.id || null,
        connection_kind: kind,
        external_groups: groups,
      }),
    });
  } catch (err) {
    // Fail open — never block authentication because of a transient
    // backend hiccup. The next login retries.
    console.log("aqp_idp_group_sync_failed:", err.message);
  }
};
```

### Wire-format the backend expects

The route `/_internal/idp/sync-groups` validates the M2M token via
the same chain as `/_internal/auth0/sync`, then for every active
`IdpConnectionRecord` of the matching `connection_kind` it looks
up matching :class:`IdpGroupMapping` rows and upserts the
corresponding :class:`Membership` rows.

### Verification

1. Stand the backend up with at least one active `IdpConnectionRecord`
   for the user's org + at least one `IdpGroupMapping` referencing
   one of the user's external groups.
2. Sign in via the matching IdP.
3. Hit `/whoami` and verify the `memberships` array contains the
   expected scope_kind / scope_id / role.
4. Query `security_audit_events`:

   ```sql
   SELECT created_at, event_type, details
   FROM security_audit_events
   WHERE event_type = 'idp_group_mapping_created'
     OR event_type = 'auth0_log_stream:s';
   ```

### Don't

- Don't bake group → role mappings into the Action body itself.
  The whole point of `IdpGroupMapping` is operator-driven mapping
  changes via the UI without redeploying Actions.
- Don't surface group lists in any visible UI or error message —
  some enterprise IdPs treat them as PII-adjacent.
- Don't enable this Action without first creating at least one
  matching `IdpConnectionRecord` in `status=active`; the route is
  a no-op without an active connection, but the Action wastes API
  call budget if it's misconfigured at scale.
