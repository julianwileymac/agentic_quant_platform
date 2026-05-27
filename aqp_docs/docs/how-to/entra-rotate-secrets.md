---
title: "Rotate Entra ID app secrets"
sidebar_position: 62
---

# Rotate Entra ID app secrets

The AQP staff Entra rollout aims for **zero stored secrets** — CI
authenticates via federated credentials (rollout plan §3.5), and the
runtime bootstrap relies on operator `az login` sessions. This page
documents:

1. The two secrets that DO exist during the bootstrap window and how
   to rotate them.
2. The federated-credential rotation cadence (no secret material, but
   subjects + issuer trust still matter).
3. The break-glass account procedure.

## What we DO NOT rotate

The aqp_entra_directory module ships zero `azuread_application_password`
resources by default. App-secret material lives in Vault under
`secret/aqp/entra/` ONLY for the bootstrap window, and ONLY when the
operator explicitly opts in via `terraform import` of an out-of-band
Azure Portal-created password. Once Phase 5 of the rollout completes,
no app secrets exist for any AQP-managed Entra app.

## Bootstrap-window secret rotation

Rotate the bootstrap SP secret used by Phase 0 / 1 of the rollout
(before federated credentials are wired):

```bash
# 1. Mint a new secret (90-day lifetime, recorded in the audit log).
NEW_SECRET="$(az ad app credential reset \
    --id "${BOOTSTRAP_SP_CLIENT_ID}" \
    --years 0 --months 3 \
    --query password -o tsv)"

# 2. Write to Vault.
vault kv put secret/aqp/entra/bootstrap_sp_secret value="${NEW_SECRET}"

# 3. Restart any service still using the old secret. Most are already
#    on federated credentials by this point so this is a sweep.
kubectl rollout restart -n aqp deploy/aqp-admin

# 4. Clear the new secret from local env.
unset NEW_SECRET
```

**Cadence**: every 90 days while Phase 0/1 secrets exist. Phase 5
retires the secret entirely.

## Federated-credential rotation

Federated credentials carry no secret material — the trust comes from
the GitHub Actions OIDC issuer + the subject claim. Rotate the
SUBJECT when:

- A repo is renamed.
- A protected branch is renamed.
- A new GitHub environment is added.

Procedure:

```hcl
# In aqp_platform/terraform/environments/wiley-tech/entra.tf,
# add a new entry to var.ci_federated_credentials:
{
  name        = "github-staging-environment"
  description = "GitHub Actions deploy to staging environment."
  subject     = "repo:julianwileymac/agentic_quant_platform:environment:staging"
}
```

Then the standard plan/apply path:

```bash
./scripts/identity/entra_terraform_plan.sh
python scripts/identity/entra_terraform_apply_via_runtime.py \
    --workspace wiley-tech \
    --apply \
    --reason "Add staging environment OIDC subject"
```

Per-environment / per-branch is **mandatory**; the module's plan
check rejects subjects containing `*` or `ref:refs/heads/*`.

## Break-glass account rotation

The two break-glass accounts (rollout plan §4 risk table) are excluded
from time-based Conditional Access policies and used ONLY in declared
incidents. Their credentials live in:

- **Physical safe** — printed sealed envelope per account.
- **Redundant FIDO2 hardware keys** — two YubiKey 5C NFC per account,
  stored in separate physical safes.

Rotation cadence: every 6 months OR after any use, whichever comes
first.

Procedure:

```bash
# 1. Generate fresh FIDO2 keys with the Azure portal / az ad device-mfa
#    enrolment flow.
# 2. Mint a fresh emergency password (UUID-derived, 24+ chars).
# 3. Update the sealed envelope in the safe.
# 4. Capture the rotation in the security log:
echo "{ \"actor\": \"$USER\", \"event\": \"break-glass-rotation\", \
       \"account\": \"break-glass-1@wiley-tech.onmicrosoft.com\", \
       \"completed_at\": \"$(date -u +%FT%TZ)\" }" \
    | gpg --encrypt -r security@aqp.fund \
    >> evidence/break-glass-rotations.gpg
```

The operator who performs the rotation runs the
`scripts/identity/list_entra_app_role_assignments.py --apps` to
confirm the break-glass account is still NOT assigned any AQP role
(the accounts MUST stay outside the AQP role surface; they exist for
tenant-level emergency access only).

## Common pitfalls

| Pitfall | Mitigation |
| --- | --- |
| Operator tempted to add a static secret for "just one workflow" | NO. File a ticket to add a federated credential subject instead |
| Forgetting to remove old federated subjects after a repo rename | Run `az ad app federated-credential list --id "${CI_APP_ID}"` quarterly; remove anything not in `var.ci_federated_credentials` |
| Break-glass account drifting into AQP role assignments | The `list_entra_app_role_assignments.py` audit script's CSV output is reviewed quarterly by Security |
| Bootstrap SP secret accidentally committed | Pre-commit hook scans for Azure-secret patterns; CI fails the PR |

## Related

- [`how-to/entra-terraform-bootstrap`](./entra-terraform-bootstrap.md) — initial setup
- [`how-to/entra-onboard-new-staff`](./entra-onboard-new-staff.md) — staff lifecycle
- [`concepts/identity/entra-internal-tenant`](../concepts/identity/entra-internal-tenant.md) — pool concept
- Long-form rollout plan with risk register:
  [`docs/plans/entra-internal-tenant-rollout.md`](pathname:///docs/plans/entra-internal-tenant-rollout.md)
