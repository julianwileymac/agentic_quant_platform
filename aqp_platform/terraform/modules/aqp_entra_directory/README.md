# `aqp_entra_directory` Terraform module

Brings the AQP staff Microsoft Entra ID tenant under Terraform control
as the **first user pool** for the managed AQP platform.

## What this module manages

| Resource | Purpose |
| --- | --- |
| `aqp-staff` app registration | Staff login app at `manage.aqp.fund` |
| `aqp-manage-api` app registration | Resource Server / token audience for the manage API |
| `aqp-ci-github` app registration | Federated-credential-only app for GitHub Actions OIDC |
| 3 service principals | One per app, with `app_role_assignment_required = true` on the manage API + CI |
| 7 app roles on `aqp-manage-api` | Admin / Operator / Auditor / Compliance / Finance / Engineer / Viewer |
| 7 directory groups | AQP-Admins / AQP-Operations / AQP-Auditors / AQP-Compliance / AQP-Finance / AQP-Engineering / AQP-SOC |
| Group → app-role assignments | Every (group, role) pair gets one `azuread_app_role_assignment` |
| Federated credentials | Per-environment / per-branch GitHub OIDC subjects (no static secrets) |
| Named locations | Trusted-IP-range definitions referenced by CA policies |
| Conditional Access policy data sources | Read-only verification that referenced CA policies exist |

## What this module does NOT manage

- **Conditional Access policy creation**. CA policies require a P2
  license + manual review by Security; this module reads them via data
  source only. Create policies in the Azure Portal, name them per the
  agreed convention (e.g. `AQP-Admins-MFA-Required`), and reference
  them from `var.ca_policy_references`.
- **Group membership**. HR + Security own group membership through the
  Azure Portal or Entitlement Management. Terraform owns *which groups
  exist + what roles they confer*; not *who is in them*.
- **Customer-tenant Entra integration**. Customer tenants flow through
  the existing `EntraTenantLink` B2B wizard (AGENTS rule 44).
- **PIM (Privileged Identity Management)**. Out of scope for the
  internal-tenant rollout; tracked as future work in
  `docs/plans/entra-internal-tenant-rollout.md` §7.

## Required IAM for the apply

The Terraform service account needs the following Microsoft Graph
roles on the AQP staff Entra tenant:

- `Application.ReadWrite.All` — create + manage app registrations
- `Group.ReadWrite.All` — create + manage groups
- `RoleManagement.ReadWrite.Directory` — assign app roles to groups
- `Policy.Read.All` — data-source read of Conditional Access policies

## Inputs

See `variables.tf`. Key inputs:

| Input | Required | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | Yes (set true) | `false` | Master switch. |
| `tenant_id` | Yes | — | Sourced from `TF_VAR_tenant_id` (Vault). |
| `tenant_primary_domain` | Yes | — | E.g. `wiley-tech.onmicrosoft.com`. |
| `staff_app.redirect_uris` | Yes | `[]` | Must include `https://manage.aqp.fund/api/auth/entra/callback`. |
| `app_role_definitions` | No | 7 canonical roles | Stable UUIDs — never regenerate. |
| `groups` | No | 7 canonical groups | Map to roles via `role_values`. |
| `ci_federated_credentials` | No | 3 default subjects | Wildcards rejected at plan time. |
| `named_locations` | No | one corp-VPN range | Used by CA policies. |
| `ca_policy_references` | No | two canonical policies | Data source only. |

See `terraform.tfvars.example` for a complete sample.

## Outputs

The module emits everything the helper scripts + settings layer need:

- `staff_app_client_id` → `auth_msal_internal_app_id`
- `tenant_id` → `auth_msal_internal_tenant_id`
- `manage_api_identifier_uri` → token audience claim verification
- `group_object_ids` → input to `aqp_admin` group-policy filters
- `summary` → compact JSON the helpers print

## Apply path

```bash
# Plan-only preview (local, no apply).
./scripts/identity/entra_terraform_plan.sh

# Apply via TerraformRuntime (writes a terraform_runs audit row).
./scripts/identity/entra_terraform_apply_via_runtime.py --target wiley-tech --reason "Phase 1 land"
```

CI applies happen through `.github/workflows/entra-terraform.yml`,
which calls the same `aqp deploy` CLI. **Never** run
`terraform apply` directly (AGENTS rule 42).

## Verifying

```bash
# Round-trip a real login.
python scripts/identity/verify_entra_login.py

# List who has which app role.
python scripts/identity/list_entra_app_role_assignments.py

# Confirm the EntraTenantLink row for the AQP tenant is `internal`.
python scripts/identity/seed_entra_internal_tenant.py --dry-run
```

## Related code

- `aqp/auth/providers/msal_entra.py` — `MSALEntraIdentityProvider`
- `aqp/persistence/models_terraform.py::EntraTenantLink`
- `aqp/auth/user.py::_apply_entra_tenant_link`
- `aqp_platform/terraform/modules/aqp_ui_identity/` — companion module
  that wires this output into the Auth0 RWA + B2B SSO surfaces
- `docs/plans/entra-internal-tenant-rollout.md` — the long-form plan
- `aqp_docs/docs/architecture/decisions/011-entra-as-first-pool.md` —
  ADR covering why Entra is the primary staff pool
