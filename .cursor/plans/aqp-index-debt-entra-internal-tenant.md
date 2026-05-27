# aqp_index debt — Entra ID internal tenant rollout

Triggered by: Workstream "Entra internal tenant"
(`docs/plans/entra-internal-tenant-rollout.md`).

## Surfaces that need a curator pass

### 1. `aqp_platform/terraform/`
- **New module**: `modules/aqp_entra_directory/` (versions / variables /
  main / outputs / README / terraform.tfvars.example).
- **Modified**: `versions.tf` adds `hashicorp/azuread` provider.
- **New**: `environments/wiley-tech/entra.tf` composes the module.
- **New**: `aqp_platform/configs/terraform/stacks/entra-internal.yaml`
  TerraformStackSpec for the apply path.
- **Modified**: `modules/aqp_ui_identity/README.md` pointer to the
  new module (the old commented-out Entra block is superseded).

### 2. `aqp/auth/providers/`
- **Modified**: `__init__.py` exports `select_provider_for_token` —
  the issuer-aware selector that routes internal-tenant tokens to
  MSAL before Auth0.

### 3. `aqp/config/settings.py`
- **New settings** (9): `auth_msal_internal_tenant_id`,
  `auth_msal_internal_app_id`, `auth_msal_internal_authority`,
  `auth_msal_internal_audience`, `auth_msal_priority`,
  `auth_msal_app_role_claim`, `auth_msal_required_ca_policies`,
  `auth_msal_internal_tenant_domain`, `auth_msal_internal_display_name`.
- `.env.example` carries the matching `AQP_AUTH_MSAL_INTERNAL_*` vars.

### 4. `scripts/identity/`
- **New helpers**:
  - `entra_terraform_plan.sh` — local plan-only preview.
  - `entra_terraform_apply_via_runtime.py` — apply via TerraformRuntime.
  - `seed_entra_internal_tenant.py` — EntraTenantLink upsert.
  - `grant_admin_consent.sh` — wrap `az ad app permission admin-consent`.
  - `verify_entra_login.py` — round-trip MSAL flow + claim check.
  - `list_entra_app_role_assignments.py` — read-only audit report.

### 5. `.github/workflows/`
- **New**: `entra-terraform.yml` — plan-on-PR + apply-via-runtime on
  push to main + workflow_dispatch.

### 6. `aqp_docs/docs/`
- **New concept page**: `concepts/identity/entra-internal-tenant.md`.
- **New how-to runbooks**: `how-to/entra-terraform-bootstrap.md`,
  `how-to/entra-onboard-new-staff.md`,
  `how-to/entra-rotate-secrets.md`.
- **New ADR**: `architecture/decisions/013-entra-as-first-pool.md`
  (number 013 because 011 + 012 were already taken).

### 7. `docs/plans/`
- **New**: `entra-internal-tenant-rollout.md` — full-depth plan with
  phases, risks, rollback procedures, SLO commitments.

## Why a curator pass is needed

This rollout introduces a NEW dimension (the AQP staff Entra tenant
as a first-class user pool) that's referenced from many places:

- The aqp_index identity-section pointers should call out
  `MSALEntraIdentityProvider` as the primary staff provider.
- The settings index should list the 9 new `auth_msal_internal_*`
  fields.
- The Terraform-modules index should add `aqp_entra_directory` next
  to `aqp_ui_identity` and `auth0_identity`.
- The scripts index should call out the six new helpers under
  `scripts/identity/`.
- The CI-workflows index should add `entra-terraform.yml`.
- The ADR index should add ADR-013 + cross-link to ADR-003 (which
  remains valid for B2C / customer fallback).

## Curator entry-point

```bash
codex run-agent aqp-index-curator \
    --reason "Entra ID internal tenant rollout (Workstream)" \
    --surfaces "aqp_platform/terraform/modules/aqp_entra_directory/, \
aqp_platform/terraform/versions.tf, \
aqp_platform/terraform/environments/wiley-tech/entra.tf, \
aqp_platform/configs/terraform/stacks/entra-internal.yaml, \
aqp/auth/providers/__init__.py, \
aqp/config/settings.py, \
.env.example, \
scripts/identity/, \
.github/workflows/entra-terraform.yml, \
aqp_docs/docs/concepts/identity/entra-internal-tenant.md, \
aqp_docs/docs/how-to/entra-terraform-bootstrap.md, \
aqp_docs/docs/how-to/entra-onboard-new-staff.md, \
aqp_docs/docs/how-to/entra-rotate-secrets.md, \
aqp_docs/docs/architecture/decisions/013-entra-as-first-pool.md, \
docs/plans/entra-internal-tenant-rollout.md"
```
