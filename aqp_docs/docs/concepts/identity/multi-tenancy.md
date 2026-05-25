---
title: 'Multi-tenancy'
summary: '```mermaid sequenceDiagram participant SPA as Vite SPA participant Entra as login.microsoftonline.com<br/>(multi-tenant) participant AQP as AQP backend participant Link as EntraTenantLink (Postgres) p...'
owner: identity-team
last_reviewed: 2026-05-25
audience: both
---

# Multi-tenancy

How AQP turns a Microsoft Entra ID `tid` claim into an
`Organization` → `Team` → `User` → `Membership` chain — and what
keeps a B2B guest from another tenant from leaking into the wrong
org.

## Identity flow

```mermaid
sequenceDiagram
  participant SPA as Vite SPA
  participant Entra as login.microsoftonline.com<br/>(multi-tenant)
  participant AQP as AQP backend
  participant Link as EntraTenantLink (Postgres)
  participant Org as Organization (Postgres)

  SPA->>Entra: PKCE auth code flow
  Entra->>SPA: id_token + access_token (carries tid + oid + roles)
  SPA->>AQP: /api/* with Bearer <access_token>
  AQP->>AQP: validate_jwt (Entra JWKS)
  AQP->>AQP: provision_user_from_claims(claims)
  AQP->>Link: lookup tid
  alt tid known + status=active
    Link-->>AQP: organization_id
    AQP->>Org: derive Memberships from roles[]
  else tid unknown + B2B enabled
    AQP->>Link: insert pending row
    AQP-->>SPA: user signs in with no memberships
    note over AQP,Link: Admin promotes link via wizard<br/>before user sees workspaces
  end
```

## Schema

| Table                   | Purpose                                                       |
| ----------------------- | ------------------------------------------------------------- |
| `organizations`         | Top of the AQP tenancy tree (multi-tenant)                    |
| `teams`                 | Subgroup within an org                                        |
| `workspaces`            | Visibility-scoped container of projects + labs                |
| `projects` / `labs`     | The user-facing buckets where strategies / RAG corpora live   |
| `users`                 | Authenticated identities (one row per Entra `oid`)            |
| `memberships`           | Polymorphic `(user, scope_kind, scope_id, role)` grants       |
| `entra_tenant_links`    | Multi-tenant Entra `tid` → AQP `organization_id` index (NEW)  |

Schema migrations:

- `0017_tenancy_foundation.py` — original `default-*` seed.
- `0050_terraform_iac_plus_entra.py` — adds `entra_tenant_links` +
  the Terraform tables.
- `0051_seed_wiley_tech.py` — seeds the canonical "Wiley Tech" org +
  user "Julian" + transfers every legacy `default-*`-owned row.

## `EntraTenantLink` lifecycle

Statuses (see :data:`ENTRA_TENANT_STATUSES`):

| Status      | Behaviour                                                                 |
| ----------- | ------------------------------------------------------------------------- |
| `pending`   | Created by first-login of an unknown `tid`. User signs in but lands on an "awaiting org admin" surface (no Memberships granted). |
| `active`    | New logins from the tenant auto-provision into the linked org + workspaces. |
| `suspended` | Sign-ins from the tenant still resolve, but no new Memberships are granted. |
| `revoked`   | Sign-ins from the tenant are blocked at provision time.                   |

AGENTS rule 44: **organization provisioning from Entra ID claims
goes through `EntraTenantLink`. Don't auto-create org rows from raw
`tid` claims.** The
`data.tenancy.link_org_to_entra_tenant` MCP tool (REST: `POST
/tenancy/entra-links`) is the only sanctioned ingress. The frontend
[`EntraTenantLinkWizard`](../aqp_client/src/components/onboarding/EntraTenantLinkWizard.tsx)
drives this flow with a 5-step wizard.

On the Auth0-federated path, the Microsoft button on the SPA login
screen uses the Auth0 Enterprise Connection
`connection=azure-ad-myorg`, which federates users to their home Entra
tenant. The Entra `tid` claim returned through Auth0 is forwarded into
the AQP access-token claim set by the Auth0 Action, and
`provision_user_from_claims` runs `_apply_entra_tenant_link` exactly as
it does in the direct-MSAL path.

For regulated deployments that bypass Auth0 and hit Entra directly,
`MsalEntraProvider` remains registered through `IdentityProviderMeta`
and activates when `AQP_AUTH_PROVIDER=msal_entra`. Both authentication
paths converge on the same backend `EntraTenantLink` lookup chain, and
super-admin promotion remains managed in
`aqp_client/src/components/onboarding/EntraTenantLinkWizard.tsx`.

## App role mapping

Entra ships app roles in a top-level `roles` claim array (e.g.
`["aqp.admin", "aqp.terraform.operator"]`). The provisioning logic
maps them onto the AQP role lattice (`viewer < editor < admin <
owner`):

```python
# aqp/auth/user.py::_apply_entra_tenant_link
# Multi-word roles fold to the tail token:
#   aqp.terraform.operator -> "operator" -> editor
#   aqp.terraform.approver -> "approver" -> admin
```

Per-link overrides live in `EntraTenantLink.role_mapping` (JSON).
Example for the seeded Wiley Tech link:

```json
{
  "aqp.admin": "owner",
  "aqp.editor": "editor",
  "aqp.viewer": "viewer",
  "aqp.terraform.operator": "editor",
  "aqp.terraform.approver": "admin"
}
```

## Onboarding wizards (frontend)

`/admin/onboarding` hosts three wizards behind tabs:

1. **OrgCreateWizard** (4 steps) — name / billing / default
   structure / review. Seeds the canonical Core team + Main
   workspace + Main project + Main lab (from
   [`configs/tenants/tenant_default_template.yaml`](../configs/tenants/tenant_default_template.yaml)).
2. **EntraTenantLinkWizard** (5 steps) — choose org / Entra tid +
   primary domain / allowed email domains / app-role mapping /
   activate.
3. **UserInviteWizard** (3 steps) — email + display name / scope +
   role / review + send (Entra B2B invitation when MSAL is
   configured).

## Tenant template files

[`configs/tenants/`](../configs/tenants/) hosts three YAMLs:

- `tenant_default_template.yaml` — default org structure created on
  `data.tenancy.create_organization`.
- `roles_default_template.yaml` — canonical app-role → AQP-role
  mapping.
- `user_invite_template.yaml` — Entra B2B invite email body + custom
  claims payload.

## Seeded state

After running `alembic upgrade head` against a fresh DB:

| Slug         | Type          | Notes                                        |
| ------------ | ------------- | -------------------------------------------- |
| `default`    | Organization  | Legacy 0017 seed (preserved for FK chains)   |
| `wiley-tech` | Organization  | New canonical seed (Wiley Tech)              |
| `core`       | Team          | Default team under wiley-tech                |
| `main`       | Workspace     | Default workspace under wiley-tech           |
| `main`       | Project       | Default project under main workspace         |
| `main`       | Lab           | Default lab under main workspace             |
| `julian@wiley.tech` | User   | Owner on every Wiley Tech scope              |

Every legacy `*_runs` / `bots` / `agent_runs_v2` / `analysis_runs` /
... row that previously pointed at `default-org` / `default-user` is
re-stamped to point at `wiley-tech` / `julian@wiley.tech` (see
`_restamp_legacy_rows` in
[`alembic/versions/0051_seed_wiley_tech.py`](../alembic/versions/0051_seed_wiley_tech.py)).
The legacy `default-*` rows stay in place so any orphan FK still
resolves.
