# Microsoft Entra ID (MSAL) setup

Step-by-step walkthrough for wiring AQP's `MsalEntraProvider` to a
multi-tenant Microsoft Entra ID app registration. The provider lives
at [`aqp/auth/providers/msal_entra.py`](../aqp/auth/providers/msal_entra.py)
and auto-registers via the
[`IdentityProviderMeta`](../aqp/auth/providers/protocol.py) metaclass.

## 1. Create the Entra app registration

1. Sign in to the [Entra admin center](https://entra.microsoft.com).
2. **Identity → Applications → App registrations → New registration**.
3. Name: `Agentic Quant Platform`.
4. Supported account types: **Accounts in any organizational
   directory + personal Microsoft accounts (B2B/B2C)**. This is
   what makes the app multi-tenant. The matching MSAL authority
   becomes `https://login.microsoftonline.com/organizations` (work /
   school accounts only) or `/common` (incl. personal accounts).
5. **Redirect URI** — add two:
   - Platform: **Web** → `https://<prod-host>/auth/callback`
   - Platform: **Single-page application (SPA)** →
     `http://localhost:3001/auth/callback` and the prod equivalent.

## 2. Generate a client secret

1. App registration → **Certificates & secrets → New client secret**.
2. Description: `aqp-backend-secret`. Expiry: max allowed (`24 months`).
3. **Copy the secret value immediately**; Entra hides it after page reload.
4. Set:
   ```
   AQP_MSAL_CLIENT_SECRET=<paste value>
   ```
   Or store it in your secret backend and reference via
   `CredentialResolver` (preferred — see
   [docs/cloud-credentials.md](cloud-credentials.md)).

## 3. Define app roles

App registration → **App roles → Create app role** (five times):

| Display name             | Member types | Value                  |
| ------------------------ | ------------ | ---------------------- |
| AQP admin                | Users / Apps | `aqp.admin`            |
| AQP editor               | Users        | `aqp.editor`           |
| AQP viewer               | Users        | `aqp.viewer`           |
| Terraform operator       | Users        | `aqp.terraform.operator` |
| Terraform approver       | Users        | `aqp.terraform.approver` |

The provider's first-login provisioning logic
([`aqp/auth/user.py::_apply_entra_tenant_link`](../aqp/auth/user.py))
maps these onto the AQP role lattice (`viewer < editor < admin <
owner`). The `aqp.terraform.*` sub-roles fold to `editor` (operator)
and `admin` (approver) by default; override via the
`EntraTenantLink.role_mapping` JSON column.

## 4. Expose an API scope

App registration → **Expose an API → Add a scope**:

- Application ID URI: `api://<app_id>` (Entra suggests this; accept).
- Scope name: `.default` (this enables the `client_credentials` grant
  used by M2M).
- Admin consent display name: `AQP API access`.

## 5. (Optional) Pre-authorize the SPA client

If you split the SPA client into its own app registration, add it to
**Expose an API → Authorized client applications** with the
`api://<app_id>/.default` scope so the token flow lands without an
admin-consent prompt.

## 6. Configure AQP

```
AQP_AUTH_PROVIDER=msal_entra
AQP_MSAL_TENANT_ID=<home tenant id (only for single-tenant mode)>
AQP_MSAL_CLIENT_ID=<app id from Overview>
AQP_MSAL_CLIENT_SECRET=<from step 2>
AQP_MSAL_AUTHORITY=https://login.microsoftonline.com/organizations
AQP_MSAL_REDIRECT_URI=https://<prod-host>/auth/callback
AQP_MSAL_SCOPES=openid profile email offline_access User.Read
AQP_MSAL_MULTI_TENANT=true
AQP_MSAL_B2B_ENABLED=true
```

Frontend Vite build:

```
VITE_MSAL_TENANT_ID=<same as backend>
VITE_MSAL_CLIENT_ID=<same as backend>
VITE_MSAL_AUTHORITY=https://login.microsoftonline.com/organizations
VITE_MSAL_REDIRECT_URI=https://<prod-host>/auth/callback
VITE_MSAL_SCOPES=openid profile email offline_access User.Read
```

## 7. Link your home Entra tenant to an AQP organization

Two paths:

1. **Frontend wizard** (recommended): navigate to
   `/admin/onboarding` → **Link Entra tenant** tab, select your AQP
   org, paste the Entra tenant id (`tid`), set primary domain +
   allowed email domains + role mapping, click "Activate".
2. **MCP tool / API**:
   ```
   POST /tenancy/entra-links
   {
     "organization_id": "<wiley-tech org id>",
     "entra_tenant_id": "<your tid>",
     "primary_domain": "wiley.tech",
     "allowed_email_domains": ["wiley.tech"],
     "role_mapping": {
       "aqp.admin": "admin",
       "aqp.editor": "editor",
       "aqp.viewer": "viewer",
       "aqp.terraform.operator": "editor",
       "aqp.terraform.approver": "admin"
     },
     "activate": true
   }
   ```

Once the link is `active`, every user that signs in from that tenant
gets a `Membership` row auto-provisioned on the linked org +
workspaces (`provider == "msal_entra"` in
[`aqp/auth/user.py::provision_user_from_claims`](../aqp/auth/user.py)).

## 8. (Optional) Conditional Access for external tenants

For B2B guest users, configure Entra Conditional Access policies on
your home tenant (MFA + IP restrictions + device compliance). AQP
does NOT enforce these — Entra denies the token before AQP sees it,
which is the correct boundary.

## 9. SCIM / Provisioning Service webhook

To pre-provision AQP users before they sign in (useful for large
orgs), point an Entra Logic App or SCIM provider at:

```
POST https://<prod-host>/_internal/msal/sync
Authorization: Bearer <m2m-token>
{
  "object_id": "<user oid>",
  "tenant_id": "<tid>",
  "email": "user@wiley.tech",
  "display_name": "User",
  "app_roles": ["aqp.editor", "aqp.terraform.operator"],
  "lifecycle_event": "created"
}
```

The endpoint is M2M-protected via `require_m2m_token` (mirrors
`/_internal/auth0/sync`) and upserts the matching `User` +
`Membership` rows so the user lands on a usable surface on their very
first request.

## Troubleshooting

| Symptom                                | Likely cause                                                          |
| -------------------------------------- | --------------------------------------------------------------------- |
| `AADSTS50194` invalid issuer           | Authority pinned to wrong tenant — use `/organizations` for multi-tenant. |
| `AADSTS65001` consent required         | Admin consent on the SPA / API scope wasn't granted.                  |
| `provision_user_from_claims` returns default user | Settings has `auth_provider != "msal_entra"`. Set the env var. |
| New user lands without org membership  | `EntraTenantLink.status == "pending"` — promote via the wizard.       |
