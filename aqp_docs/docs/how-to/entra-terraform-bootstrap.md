---
title: "Bootstrap the AQP Entra ID staff tenant"
sidebar_position: 60
---

# Bootstrap the AQP Entra ID staff tenant

Step-by-step procedure for taking the AQP staff Microsoft Entra ID
tenant from "exists in the Azure Portal" to "fully Terraform-controlled
and serving as the first user pool for `manage.aqp.fund`".

This is the implementation runbook. Concept context lives at
[`concepts/identity/entra-internal-tenant`](../concepts/identity/entra-internal-tenant.md);
the full rollout schedule + risks + rollback at
[`docs/plans/entra-internal-tenant-rollout.md`](pathname:///docs/plans/entra-internal-tenant-rollout.md).

## Pre-requisites

| Prereq | How to confirm |
| --- | --- |
| AQP staff Entra tenant exists | `az account tenant list` shows the tenant id |
| Global admin / Application Administrator account | `az ad signed-in-user show` confirms role assignment |
| Bootstrap service principal exists with `Application.ReadWrite.All` + `Group.ReadWrite.All` + `RoleManagement.ReadWrite.Directory` | `az ad sp show --id <sp-id>` |
| Terraform 1.10+ installed locally | `terraform version` |
| Repo cloned + AQP runtime installable | `pip install -e .[dev]` succeeds |
| Vault accessible with the `secret/aqp/entra/` mount | `vault kv get secret/aqp/entra/internal_tenant_id` resolves |

If any prereq is missing, file a ticket with the Identity team
(reference ADR-011) before continuing.

## Step 1 — Set environment variables

```bash
# Sourced from Vault by the operator before running the helpers.
export AZURE_TENANT_ID="<aqp-staff-tenant-guid>"
export AZURE_CLIENT_ID="<bootstrap-sp-client-id>"
export AZURE_CLIENT_SECRET="<bootstrap-sp-secret>"   # OR use az login

# Echoed into the Terraform provider.
export TF_VAR_entra_tenant_id="${AZURE_TENANT_ID}"
export TF_VAR_entra_enabled="true"
```

> **Note**: the `AZURE_CLIENT_SECRET` path is documented for the
> bootstrap window only. Once the `aqp-ci-github` app registration +
> federated credentials land (Phase 5 of the rollout plan), no secret
> is stored anywhere; CI authenticates via OIDC.

## Step 2 — Plan-only preview

```bash
./scripts/identity/entra_terraform_plan.sh
```

The script:

1. Runs `terraform fmt -check` + `terraform validate` against the
   module.
2. Runs `terraform plan -target=module.aqp_entra_directory` against
   the `wiley-tech` environment.
3. Writes the plan binary to `/tmp/aqp-entra-wiley-tech.plan` and
   prints the next-step command.

Inspect the plan line-by-line. Common red flags:

- A resource shows `# forces replacement` for an app-role id → someone
  has regenerated a UUID in `var.app_role_definitions` (DON'T merge).
- A federated credential shows `subject = "...:*"` → wildcard rejected
  by the module check; fix the input.
- A group display name conflicts with an existing group → rename or
  import.

## Step 3 — Apply via TerraformRuntime

```bash
python scripts/identity/entra_terraform_apply_via_runtime.py \
    --workspace wiley-tech \
    --apply \
    --reason "Phase 2 land for entra-internal stack"
```

The helper:

1. Loads the `entra-internal` `TerraformStackSpec`.
2. Runs `runtime.plan(...)` (writes a `terraform_runs` row).
3. Prompts for `yes` confirmation (skip with `--yes` only in CI).
4. Runs `runtime.apply(...)` (writes a second `terraform_runs` row
   linked to the same spec_version_id).

Output is redacted: token-bearing fields show only the first 4
characters per AGENTS rule 26.

## Step 4 — Grant admin consent

After the apps land, their requested Microsoft Graph permissions are
*requested* but not yet *consented*. Grant tenant-wide consent:

```bash
# The staff app's client_id is in the Terraform output:
STAFF_CID="$(terraform -chdir=aqp_platform/terraform/environments/wiley-tech \
                output -raw entra_staff_app_client_id)"

./scripts/identity/grant_admin_consent.sh "${STAFF_CID}"
```

The script wraps `az ad app permission admin-consent` and verifies
the resulting grants with `az ad app permission list-grants`.

## Step 5 — Seed `EntraTenantLink`

```bash
# Read the new staff app's tenant id and stamp the canonical row.
export AQP_AUTH_MSAL_INTERNAL_TENANT_ID="${AZURE_TENANT_ID}"
export AQP_AUTH_MSAL_INTERNAL_APP_ID="${STAFF_CID}"

python scripts/identity/seed_entra_internal_tenant.py --dry-run
python scripts/identity/seed_entra_internal_tenant.py --apply
```

Idempotent: the second `--apply` is a no-op if the row already matches
the target shape.

## Step 6 — Round-trip a real login

```bash
# Browser flow.
python scripts/identity/verify_entra_login.py

# Headless / SSH session.
python scripts/identity/verify_entra_login.py --device-code
```

Successful output:

```
INFO Got access token: eyJ0… (1456 chars)
INFO Claims look correct.
INFO CA policies found: AQP-Admins-MFA-Required, AQP-Block-Risky-Sign-Ins
INFO All checks passed.
```

If a CA policy is missing, the script exits with code 4 and lists the
missing policies. Add them via the Azure Portal under Security review,
then re-run. CA policies are NOT created from Terraform (rollout plan
§1.2).

## Step 7 — Verify role assignments

```bash
python scripts/identity/list_entra_app_role_assignments.py
```

Should print one row per (group, role) pair the module created. Save
a CSV snapshot for the audit trail:

```bash
python scripts/identity/list_entra_app_role_assignments.py \
    --format=csv > evidence/entra-role-snapshot-$(date +%F).csv
```

## Step 8 — Switch the manage.aqp.fund chooser to prefer Entra

With everything in place, flip the runtime so the `manage.aqp.fund`
login chooser prefers Entra over Auth0:

```bash
# Settings already wired in aqp/config/settings.py:
#   auth_msal_priority = 100   # MSAL wins
#   auth_msal_internal_*       # populated from Terraform outputs

kubectl set env -n aqp deploy/aqp-admin \
    AQP_AUTH_MSAL_INTERNAL_TENANT_ID="${AZURE_TENANT_ID}" \
    AQP_AUTH_MSAL_INTERNAL_APP_ID="${STAFF_CID}" \
    AQP_AUTH_MSAL_INTERNAL_AUTHORITY="https://login.microsoftonline.com/${AZURE_TENANT_ID}" \
    AQP_AUTH_MSAL_INTERNAL_AUDIENCE="api://aqp-manage-api" \
    AQP_AUTH_MSAL_PRIORITY=100

kubectl rollout status -n aqp deploy/aqp-admin
```

24-hour bake: monitor the
`auth_login_total{provider="entra"}` and
`auth_login_failure_total` Prometheus counters. ≥95% of staff logins
should land on Entra after the bake.

## Verification

| Check | Command |
| --- | --- |
| Terraform plan is clean | `./scripts/identity/entra_terraform_plan.sh` (no diff) |
| `terraform_runs` audit row recorded | `psql -c "SELECT id, status FROM terraform_runs WHERE stack_slug='entra-internal' ORDER BY created_at DESC LIMIT 1"` |
| `entra_tenant_links` has `kind=internal` | `python scripts/identity/seed_entra_internal_tenant.py --dry-run` reports `EXISTING row matches target` |
| Real login works end-to-end | `python scripts/identity/verify_entra_login.py` exits 0 |
| All seven groups have role assignments | `python scripts/identity/list_entra_app_role_assignments.py` prints ≥7 rows |

## Rollback

See [the rollout plan §5](pathname:///docs/plans/entra-internal-tenant-rollout.md)
for the three rollback tiers (hot / cold / catastrophic).
