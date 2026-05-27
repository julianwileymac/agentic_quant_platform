# aqp_ui_identity

Terraform module that provisions the Auth0 Regular Web Application
backing the `aqp_ui` cloud frontend (B2C / customer pool).

> **Note**: the Microsoft Entra ID surface that used to be sketched here
> as a commented-out block has moved to its own module
> [`aqp_entra_directory`](../aqp_entra_directory/README.md). That module
> covers the AQP **internal** staff tenant (rule 27 / rule 44 / rule 42)
> and is the **first user pool** for `manage.aqp.fund`. Customer-tenant
> Entra integration continues to flow through the `EntraTenantLink` B2B
> approval wizard at runtime.
>
> See `docs/plans/entra-internal-tenant-rollout.md` for the
> long-form rollout plan and
> `aqp_docs/docs/architecture/decisions/011-entra-as-first-pool.md` for
> the ADR.

## When to use

Wire this module into a target environment (e.g.
`aqp_platform/terraform/environments/<env>/main.tf`) when you are ready
to expose `aqp_ui` publicly under `aqp.fund`, `www.aqp.fund`, and
`app.aqp.fund`.

Until then, leave `enabled = false` (the default).

## Usage

```hcl
module "aqp_ui_identity" {
  source = "../../modules/aqp_ui_identity"

  enabled        = true
  domain         = "aqp-fund.us.auth0.com"
  api_identifier = "https://api.aqp.internal/manage"

  callback_urls = [
    "https://aqp.fund/api/auth/auth0/callback",
    "https://www.aqp.fund/api/auth/auth0/callback",
    "https://app.aqp.fund/api/auth/auth0/callback",
    "http://localhost:3002/api/auth/auth0/callback",
  ]
  logout_urls = [
    "https://aqp.fund",
    "https://www.aqp.fund",
    "https://app.aqp.fund",
    "http://localhost:3002",
  ]
  web_origins = [
    "https://aqp.fund",
    "https://www.aqp.fund",
    "https://app.aqp.fund",
    "http://localhost:3002",
  ]

  # B2B Entra SSO support — set entra_enabled = true after pinning
  # the `azuread` provider in aqp_platform/terraform/versions.tf.
  entra_enabled = false
}
```

## Boundaries

- AGENTS rule 26 (CredentialResolver): the generated `client_secret`
  output is sensitive. Pipe it into the Vault store at
  `secret/data/aqp-ui/auth0:client_secret` via an out-of-band step (e.g.
  `terraform output -raw client_secret | vault kv put ...`). Never
  commit it.
- AGENTS rule 27 (IdentityProvider): this module owns ONLY the Auth0
  side. JWT validation is performed by the upstream FastAPI through
  the existing `auth0-fastapi-api` validator chain. aqp_ui holds the
  session cookie and never validates JWTs itself.
- AGENTS rule 44 (EntraTenantLink): even with `entra_enabled = true`,
  customer tenants are NOT auto-provisioned. The first sign-in from a
  new `tid` creates a `pending` `EntraTenantLink` row; an AQP
  super-admin promotes it through `aqp_admin`.

## CI gating

The module is `enabled = false` by default so accidental `terraform
apply` runs in dev environments don't burn through Auth0 client quotas
or create dangling Entra app registrations. Flip to `true` only in the
production environment after the supplier completes:

1. Auth0 tenant exists (`aqp-fund.us.auth0.com`).
2. The base `auth0_identity` module has applied (API + M2M client + roles).
3. Vault has empty stubs at `secret/data/aqp-ui/{auth0,entra,session}`.
4. External Secrets Operator is healthy in the `aqp-ui` namespace.
