---
title: 'Auth0 setup — comprehensive operator runbook'
summary: 'The platform supports three deployment shapes:'
owner: identity-team
last_reviewed: 2026-05-25
audience: both
---

# Auth0 setup — comprehensive operator runbook

This is the canonical setup guide for AGENTS hard rules 52-55 (the
Phase 5+ auth refactor). Pair with
[aqp_docs/auth0-actions.md](../../concepts/identity/auth0-actions.md) for the JS Action bodies
that go in the Auth0 Dashboard.

The platform supports three deployment shapes:

- **Local-first dev**: `AQP_AUTH_PROVIDER=local`, no Auth0 tenant
  needed. Everything below is skipped.
- **Single-tenant B2C**: one Auth0 tenant per env, individual users
  sign up via Universal Login + social connections. Organizations
  is OFF (or "Allow individual logins" if you want both modes).
- **Multi-tenant B2B**: same Auth0 tenant per env, institutional
  customers attach via Auth0 Organizations. Each Organization has
  its own branded login + Enterprise connection.

The same backend serves all three; the difference is purely the
Auth0 configuration + the `AQP_AUTH_*` env vars.

---

## 1. Tenants

One Auth0 tenant per AQP environment. Three tenants per AGENTS rule:

| Env | Auth0 tenant | Custom domain | Issuer URL in `AQP_AUTH_OIDC_ISSUER` |
| --- | --- | --- | --- |
| dev | `aqp-dev` | `auth.dev.aqp.fund` | `https://auth.dev.aqp.fund/` |
| stage | `aqp-stage` | `auth.stage.aqp.fund` | `https://auth.stage.aqp.fund/` |
| prod | `aqp-prod` | `auth.aqp.fund` | `https://auth.aqp.fund/` |

Custom domains stabilise the issuer URL so changing Auth0 tenants
later is non-breaking. Without a custom domain the issuer is
`https://aqp-prod.us.auth0.com/` and every existing JWT cache /
revocation token has to be invalidated on rebrand.

Never share Auth0 tenants across envs — Auth0 charges per MAU per
tenant, but the security boundary is more important than the cost
arithmetic.

---

## 2. API resource server

One API record per tenant — the AQP backend.

| Field | Value (prod example) |
| --- | --- |
| Name | `aqp-api` |
| Identifier | `https://api.aqp.fund/` |
| Signing algorithm | `RS256` |
| Allow Skipping User Consent | ON |
| Allow Offline Access | ON |
| Token expiration (seconds) | `86400` (24h ceiling — per-app overrides win) |
| Token expiration for browser flows (seconds) | `7200` (2h SPA ceiling) |

Enable **RBAC**:

- Settings → "Enable RBAC" → ON
- Settings → "Add Permissions in the Access Token" → ON

Define every permission AQP uses (Permissions tab):

```
read:portfolio             Read portfolio positions / PnL / risk
write:portfolio            Mutate portfolio config
read:strategy              Read strategy specs / backtest history
write:strategy             Author / edit strategies
deploy:strategy            Promote a strategy to live trading
kill_switch:execute        Engage the global kill switch
trade:execute              Submit live or paper orders
trade:live                 Bypass the paper-only guard
read:mcp:data              Invoke the Data MCP tools
write:mcp:data             Mutate via Data MCP (e.g. namespace policy edits)
read:mcp:codebase          Invoke the Codebase MCP tools
write:mcp:codebase         Apply code edits via Codebase MCP (rarely granted)
run:agent                  Spawn an AgentRuntime
admin:tenant               Org-admin powers (invites, IdP config, billing)
admin:cluster              Bypass resource filter; superadmin-only
manage:broker_credentials  Read/write broker credentials at org scope
read:logs                  Required for the Auth0 Management API M2M client
```

Add Token Exchange:

- API → Settings → "Token Exchange" → ON (required for
  `aqp-agent-broker` to use RFC 8693).

---

## 3. Applications

Five application records per tenant:

| Record | Type | Grants | Token TTL | Notes |
| --- | --- | --- | --- | --- |
| `aqp-spa` | Single Page Application | `authorization_code` + `refresh_token` | access 15m, ID 10m | Refresh-token rotation ON, absolute lifetime 24h |
| `aqp-cli` | Native | `urn:ietf:params:oauth:grant-type:device_code` + `refresh_token` | access 60m | Rotation ON, absolute 30d, inactivity 7d. **"Business Users" mode** so Device Code stays compatible with Orgs |
| `aqp-backend-m2m` | M2M | `client_credentials` | 24h | For internal service-to-service + Auth0 Management API |
| `aqp-action-callback-m2m` | M2M | `client_credentials` | 5m | Used inside Auth0 Actions for `/_internal/auth0/sync` |
| `aqp-agent-broker` | M2M | `client_credentials` + `urn:ietf:params:oauth:grant-type:token-exchange` | 5m | RFC 8693 delegated-agent-token minting |

### 3.1 `aqp-spa` (SPA)

- Application URIs:
  - Allowed callback URLs:
    `https://app.aqp.fund/auth/callback`, `http://localhost:3001/auth/callback`
  - Allowed logout URLs: `https://app.aqp.fund/`, `http://localhost:3001/`
  - Allowed web origins: `https://app.aqp.fund`, `http://localhost:3001`
- Refresh Token Rotation: ON
- Refresh Token Expiration: Absolute 24h
- Refresh Token Inactivity: 7d
- Idle Session Lifetime: 72h
- Maximum Session Lifetime: 168h (7d)

Frontend env vars (Vite):

```
VITE_AUTH_PROVIDER=auth0
VITE_AUTH0_DOMAIN=auth.aqp.fund          # custom domain
VITE_AUTH0_SPA_CLIENT_ID=<aqp-spa client_id>
VITE_AUTH0_AUDIENCE=https://api.aqp.fund/
VITE_AUTH0_SCOPE=openid profile email offline_access read:portfolio write:portfolio read:strategy write:strategy read:mcp:data
VITE_AUTH0_ORGANIZATION=                  # B2B only — pin to a single org
```

### 3.2 `aqp-cli` (Native)

- Connections tab: enable the same DB / social connections as the SPA.
- Advanced Settings → Grant Types: enable `Device Code` + `Refresh Token`.
- "Business Users" mode (not "Organizations Required"); the Auth0
  team's M2M-for-Orgs GA notes that Device Code is incompatible
  with the strict "Organizations Required" setting.

CLI env vars (operator's machine):

```
AQP_CLI_OIDC_DOMAIN=auth.aqp.fund
AQP_CLI_OIDC_CLIENT_ID=<aqp-cli client_id>
AQP_CLI_OIDC_AUDIENCE=https://api.aqp.fund/
AQP_CLI_OIDC_ORGANIZATION=                # B2B: pin to a single org
```

The CLI fetches all three from `/auth/config` when not set, so most
operators don't need to copy-paste.

### 3.3 `aqp-backend-m2m` (M2M)

- Authorise against:
  - `aqp-api` (all permissions the backend needs to act on its own behalf).
  - Auth0 Management API (`read:users`, `update:users`, `delete:sessions`,
    `read:sessions`, `read:logs`, `read:connections`,
    `create:guardian_enrollment_tickets`, `delete:guardian_enrollments`,
    `create:user_tickets`).

Backend env vars:

```
AQP_AUTH_PROVIDER=auth0
AQP_AUTH_OIDC_ISSUER=https://auth.aqp.fund/
AQP_AUTH_OIDC_AUDIENCE=https://api.aqp.fund/
AQP_AUTH_OIDC_CLIENT_ID=<aqp-spa client_id>     # SPA client_id (for the SPA-targeted JWKS validation path)
AQP_AUTH_OIDC_CLIENT_SECRET=                    # empty — SPAs are public clients
AQP_AUTH0_MGMT_API_AUDIENCE=https://aqp-prod.us.auth0.com/api/v2/
AQP_AUTH0_MGMT_API_CLIENT_ID=<aqp-backend-m2m client_id>
AQP_AUTH0_MGMT_API_CLIENT_SECRET=               # via CredentialResolver in prod; env in dev
AQP_AUTH0_DPOP_ENABLED=true                     # SDK mixed-mode
AQP_AUTH0_DPOP_REQUIRED=false                   # flip true after CLI + SPA migrate
AQP_AUTH_M2M_ENABLED=true
AQP_AUTH_M2M_AUDIENCE=https://api.aqp.fund/
AQP_AUTH_STEP_UP_ENABLED=true
AQP_AUTH_STEP_UP_DEFAULT_MAX_AGE=180
```

### 3.4 `aqp-action-callback-m2m` (M2M)

Same scopes as `aqp-backend-m2m` but used INSIDE Auth0 Actions to
call `/_internal/auth0/sync` + `/_internal/idp/sync-groups`. The
Action body in [auth0-actions.md](../../concepts/identity/auth0-actions.md) shows how to
mint + cache the token.

### 3.5 `aqp-agent-broker` (M2M for Token Exchange)

- Grants: `client_credentials` + `urn:ietf:params:oauth:grant-type:token-exchange`.
- Authorised APIs: `aqp-api` with scopes
  `read:mcp:data`, `write:mcp:data`, `read:mcp:codebase`, `write:mcp:codebase`.
- Used ONLY by the Custom Token Exchange Profile body to mint
  delegated agent tokens.

Backend env vars:

```
AQP_AUTH_AGENT_TOKEN_EXCHANGE_ENABLED=true
AQP_AUTH_AGENT_BROKER_CLIENT_ID=<aqp-agent-broker client_id>
AQP_AUTH_AGENT_BROKER_CLIENT_SECRET=           # via CredentialResolver in prod
AQP_AUTH_AGENT_DELEGATION_TTL_SECONDS=300
```

---

## 4. Connections

### Database connection (B2C)

- Default `Username-Password-Authentication` database connection.
- Password Strength: "Excellent" (NIST 800-63 compliant).
- Enable: "Disable Signups from Public Signup Page" if you want
  invite-only onboarding (B2B-heavy deployments).

### Social connections (B2C)

- GitHub, Google (`google-oauth2`). Both default to the standard
  Auth0 connection types — no extra config beyond the Client ID +
  Secret from the respective developer console.

### Enterprise connections (B2B)

Configured per-org in :class:`IdpConnectionRecord`. Auth0 supports
SAML, ADFS, Azure AD (Entra), Google Workspace, PingFederate,
SiteMinder, Okta Workforce Identity, OneLogin, JumpCloud,
generic OIDC. The AQP-side admin UI is
[`IdpGroupMappingEditor`](../aqp_client/src/components/onboarding/IdpGroupMappingEditor.tsx).

Each enterprise connection MUST:

- Sync the user's group claims (Azure `groups`, Google's group claim,
  Okta `groups`). The Action `aqp-idp-group-sync` reads them.
- Map to a single AQP Organization via the matching
  :class:`IdpConnectionRecord.organization_id`. Multiple orgs may
  use the same connection KIND (e.g. AcmeCorp Okta + Subsidiary
  Okta) but each is a separate record.

---

## 5. Organizations (B2B)

One Auth0 Organization per institutional tenant. Auth0 charges per
Org per month on most tiers — budget accordingly.

| Setting | Value |
| --- | --- |
| Membership on Login | "Require Members to use this Organization" (strict B2B) |
| Allowed Connections | Only the org's enterprise connection(s) |
| Branding | Per-org logo + colors so users land on a branded login |

Use `?organization=org_xxx&login_hint=user@acme.com` on `/authorize`
to skip the org-picker step. The SPA reads
`VITE_AUTH0_ORGANIZATION` to pin.

The post-login Action (`aqp-post-login`) reads `event.organization?.id`
and injects it as `https://aqp.internal/org_id` so the FastAPI
`require_org` dep can branch immediately.

---

## 6. Actions

Three Login-trigger Actions (in this order):

1. **`aqp-post-login`** — JIT user upsert + custom claim injection.
   Body in [auth0-actions.md](../../concepts/identity/auth0-actions.md) ("Phase 7 post-login
   Action" section, extended by "Phase 8" addendum for step-up MFA).

2. **`aqp-idp-group-sync`** — reads external IdP group claims and
   posts to `/_internal/idp/sync-groups` so the AQP backend upserts
   matching Membership rows per the per-org IdpGroupMapping table.
   Body in [auth0-actions.md](../../concepts/identity/auth0-actions.md) ("Phase 6 — IdP
   group sync Action" section).

And one Custom Token Exchange Profile:

3. **`aqp-agent-delegation`** — RFC 8693 minting for delegated
   agent tokens. Body in
   [auth0-actions.md](../../concepts/identity/auth0-actions.md) ("Phase 8 — Custom Token
   Exchange Profile" section).

---

## 7. Pre-User-Registration trigger

One Action to block disposable emails + verify B2B invites:

```javascript
exports.onExecutePreUserRegistration = async (event, api) => {
  const email = (event.user.email || "").toLowerCase();
  const disposable = ["mailinator.com", "guerrillamail.com", "tempmail.org",
                      "10minutemail.com", "throwaway.email"];
  const domain = email.split("@")[1];
  if (!email) { api.access.deny("invalid_email", "email required"); return; }
  if (disposable.includes(domain)) {
    api.access.deny("disposable_email", "disposable email domains not allowed");
    return;
  }
  // B2B invite verification — operator chooses how strict.
  if (event.client.metadata?.flow === "b2b" && event.secrets.AQP_BACKEND_URL) {
    // Call /_internal/auth/preregister-check (operator adds this route
    // if they want HMAC-based invite enforcement at registration time).
  }
};
```

---

## 8. Log Streams

One **Custom Webhook** log stream per env:

| Field | Value |
| --- | --- |
| Type | Custom Webhook |
| Payload URL | `https://api.aqp.fund/_internal/auth0/log-stream` |
| Authorization | `Bearer <secret>` (matches `AQP_AUTH0_LOG_STREAM_SECRET`) |
| Content Type | `application/json` |
| Custom Headers | (none beyond Authorization) |
| Filter | All events (the backend filters server-side) |

Operator generates the shared secret:

```
openssl rand -hex 32
```

…then sets it both in the Auth0 Dashboard webhook config AND in
the backend's `AQP_AUTH0_LOG_STREAM_SECRET` env var. The HMAC
compare on `_verify_authorization` rejects any other value.

Optionally also wire native Datadog / Splunk / Elastic streams for
the SIEM team — those are independent of the AQP webhook.

---

## 9. Adaptive MFA

Security → Multi-factor Authentication → Adaptive MFA → ON.

| Risk level | Action | Why |
| --- | --- | --- |
| `low` | Allow (no MFA) | Normal session resumption |
| `medium` | MFA challenge | Suspicious-but-not-definitive signals |
| `high` | MFA challenge | Likely compromised |

Enabled MFA factors (Security → Multi-factor Authentication → Factors):

- **OTP (TOTP)** — always-on; required for every B2B user
- **WebAuthn** — recommended primary for B2B users
- **Push** (Auth0 Guardian app) — B2C convenience
- **SMS** — discouraged for B2B; allow as B2C fallback only
- **Email OTP** — convenient B2C fallback
- **Recovery codes** — always issue alongside any factor

The `aqp-post-login` Action's Phase 8 addendum calls
`api.multifactor.enable("any", { allowRememberBrowser: false })`
when the SPA / CLI requests `acr_values=http://schemas.openid.net/pape/policies/2007/06/multi-factor`
on `/authorize`. This is the integration point for the backend's
`require_step_up` dep.

---

## 10. Env-var checklist (prod)

```
# IdP
AQP_AUTH_PROVIDER=auth0
AQP_AUTH_REQUIRED=true
AQP_AUTH_ENFORCE=strict
AQP_AUTH_OIDC_ISSUER=https://auth.aqp.fund/
AQP_AUTH_OIDC_AUDIENCE=https://api.aqp.fund/
AQP_AUTH_OIDC_CLIENT_ID=<aqp-spa client_id>
AQP_AUTH_CLAIMS_NAMESPACE=https://aqp.internal/
AQP_AUTH_CLAIMS_NAMESPACE_ALIASES=https://aqp/   # CSV; legacy reader

# Management API
AQP_AUTH0_MGMT_API_AUDIENCE=https://aqp-prod.us.auth0.com/api/v2/
AQP_AUTH0_MGMT_API_CLIENT_ID=<aqp-backend-m2m client_id>
AQP_AUTH0_MGMT_API_CLIENT_SECRET=                # via CredentialResolver

# M2M
AQP_AUTH_M2M_ENABLED=true
AQP_AUTH_M2M_AUDIENCE=https://api.aqp.fund/
AQP_AUTH_M2M_TOKEN_TTL_SECONDS=900

# DPoP
AQP_AUTH0_DPOP_ENABLED=true
AQP_AUTH0_DPOP_REQUIRED=false                   # flip true once SDK rolled out
AQP_DPOP_ENFORCEMENT_ENABLED=false              # per-route enforcement

# Step-up MFA (rule 52)
AQP_AUTH_STEP_UP_ENABLED=true
AQP_AUTH_STEP_UP_DEFAULT_MAX_AGE=180

# Auth0 Log Stream (rule 53)
AQP_AUTH0_LOG_STREAM_SECRET=<openssl rand -hex 32>
AQP_AUTH0_LOG_STREAM_MAX_AGE_SECONDS=86400

# Delegated agent tokens (rule 54)
AQP_AUTH_AGENT_TOKEN_EXCHANGE_ENABLED=true
AQP_AUTH_AGENT_BROKER_CLIENT_ID=<aqp-agent-broker client_id>
AQP_AUTH_AGENT_BROKER_CLIENT_SECRET=             # via CredentialResolver
AQP_AUTH_AGENT_DELEGATION_TTL_SECONDS=300

# B2B Entra (existing)
AQP_AUTH_MSAL_B2B_ENABLED=true

# Tenancy
AQP_TENANCY_DEFAULT_STRATEGY=hybrid
AQP_TENANCY_RLS_ENFORCE=strict                   # was off; flip after Phase 5 verified

# MCP RFC conformance
AQP_MCP_DATA_CANONICAL_URI=https://api.aqp.fund/mcp/data
AQP_MCP_CODEBASE_CANONICAL_URI=https://api.aqp.fund/mcp/codebase
AQP_MCP_REQUIRE_RFC8707=strict                   # was off

# Per-user OAuth wizard
AQP_USER_OAUTH_ENABLED=true

# Audit
AQP_AUTH_AUDIT_ENABLED=true
AQP_AUTH_AUDIT_RETENTION_DAYS=365
```

---

## 11. CLI env vars (per operator)

```
AQP_CLI_OIDC_DOMAIN=auth.aqp.fund
AQP_CLI_OIDC_CLIENT_ID=<aqp-cli client_id>
AQP_CLI_OIDC_AUDIENCE=https://api.aqp.fund/
AQP_CLI_OIDC_ORGANIZATION=                        # B2B: pin to a single org
# Headless / CI fallback (no keyring backend):
AQP_CLI_AUTH_ALLOW_PLAINTEXT_FALLBACK=0
```

---

## 12. Rollout order

| Step | Action | Verification |
| --- | --- | --- |
| 1 | Create dev tenant + apps + custom domain | `/auth/config` returns the tenant id |
| 2 | Backend up with `AQP_AUTH_ENFORCE=permissive` | Existing routes still serve; 401 dashboard shows zero would-be denies |
| 3 | Flip `AQP_AUTH_ENFORCE=strict` | Unauthenticated calls return 401 |
| 4 | Wire Auth0 log-stream webhook + Action triggers | Force a session-revoke in Dashboard; verify `cleanup_for_user` Celery row + audit row |
| 5 | Enable `AQP_AUTH_STEP_UP_ENABLED=true` | Click kill-switch → MFA prompt; complete it; subsystems halt |
| 6 | Enable `AQP_AUTH_AGENT_TOKEN_EXCHANGE_ENABLED=true` + create Profile | Trigger an agent that calls a DataMCP tool; verify `act` claim in `/mcp/data` response body + `delegation` JSON in audit |
| 7 | Enable `AQP_USER_OAUTH_ENABLED=true` | `/me/oauth-connections/providers` returns the 5 providers |
| 8 | Enable BYOK broker credentials (run Alembic 0065) | Add an Alpaca paper key; smoke-test a paper trade |
| 9 | Enable RLS strict mode (`AQP_TENANCY_RLS_ENFORCE=strict`) | Existing test workspace queries still work; cross-workspace fetches return zero rows |
| 10 | Enable MCP RFC 8707 strict mode | MCP calls with mis-audienced tokens return 401 + WWW-Authenticate header |

Each flip is independently reversible.

---

## 13. Reference docs

- [aqp_docs/auth0-actions.md](../../concepts/identity/auth0-actions.md) — Action bodies + the
  Custom Token Exchange Profile setup.
- [aqp_docs/identity.md](../../concepts/identity/identity.md) — the full identity stack.
- [aqp_docs/multi-tenancy.md](../../concepts/identity/multi-tenancy.md) — Organization →
  EntraTenantLink → User → Membership flow.
- [aqp_docs/credentials.md](../../concepts/identity/credentials.md) — how M2M + BYOK
  credentials flow through CredentialResolver.
- [.cursor/rules/identity.mdc](../.cursor/rules/identity.mdc) — the
  always-on identity-enforcement rule.
- [.cursor/rules/auth-stepup-and-byok.mdc](../.cursor/rules/auth-stepup-and-byok.mdc)
  — Phase 5+ rules (52-55) scoped to the new module files.
- [AGENTS.md](https://github.com/julianwileymac/agentic_quant_platform/blob/main/AGENTS.md) — hard rules 27, 44, 45, 50, 51, 52-55.
