---
title: "Onboard a new staff member into Entra"
sidebar_position: 61
---

# Onboard a new staff member into Entra

Procedure for adding a new AQP employee to the company's Entra
directory and granting them the right level of access to the managed
AQP platform.

This is a HR + Security workflow that does NOT touch Terraform.
Group membership is intentionally outside Terraform's purview (rollout
plan §1.2); Terraform owns *which groups exist + what roles they
confer*, not *who is in them*.

## Inputs

- The new hire's full name + corporate email address.
- Their HR-side role (engineer, ops, compliance, finance, …).
- The hiring manager's approval (capture the ticket id for the audit).

## Steps

### 1. Create the Entra user

If the new hire doesn't already have an Entra account from corporate
onboarding, create one:

```bash
az ad user create \
    --display-name "First Last" \
    --user-principal-name first.last@wiley-tech.onmicrosoft.com \
    --password "$(uuidgen | tr -d '-' | head -c 24)Aa!1" \
    --force-change-password-next-sign-in true
```

The auto-generated password is changed on first login; the operator
NEVER stores or shares it.

### 2. Add to the appropriate AQP group

Map the HR-side role to the canonical group. Default mappings:

| HR role | Entra group(s) |
| --- | --- |
| Software Engineer / SRE | `AQP-Engineering` |
| Senior SRE / on-call rotation | `AQP-Engineering` + `AQP-Operations` |
| Compliance Officer | `AQP-Compliance` |
| Internal Auditor | `AQP-Auditors` |
| Finance / FinOps | `AQP-Finance` |
| Security Engineer | `AQP-SOC` |
| CTO / VP Engineering | `AQP-Admins` (requires CTO sign-off and CA-policy MFA) |

Add via the Azure Portal **OR** via CLI:

```bash
# Look up the group id (cached locally for repeat use).
GROUP_ID="$(az ad group show --group AQP-Engineering --query id -o tsv)"
USER_ID="$(az ad user show --id first.last@wiley-tech.onmicrosoft.com --query id -o tsv)"
az ad group member add --group "${GROUP_ID}" --member-id "${USER_ID}"
```

### 3. Verify the role propagation

Wait 5 minutes for Entra to propagate, then have the new hire sign in
once at `manage.aqp.fund`. The application token they receive should
include the `roles` claim mapped to the group.

Confirm from the operator side:

```bash
python scripts/identity/list_entra_app_role_assignments.py \
    --format=json \
    | jq '.[] | select(.principal_display_name=="First Last")'
```

Should print one row per (role) for each group the user is in.

### 4. Capture the audit trail

The Entra audit log records group-membership changes automatically and
forwards them to the corporate SIEM via the existing log stream. The
manager's approval ticket gets attached as part of the standard
employee onboarding packet.

## Promoting an existing staff member

```bash
# Add to a higher-privilege group (e.g. ops on-call).
az ad group member add --group AQP-Operations --member-id "${USER_ID}"
```

For promotions to `AQP-Admins`:

1. The CTO must sign off in writing (ticket id captured).
2. The user must have a registered FIDO2 hardware key (verified by
   the Security team).
3. The user falls under the `AQP-Admins-MFA-Required` Conditional
   Access policy automatically.

## Off-boarding

```bash
# Remove from every AQP group; do NOT just disable the Entra account
# in case the user has cross-tenant memberships we don't manage.
for group in AQP-Engineering AQP-Operations AQP-Auditors AQP-Compliance \
             AQP-Finance AQP-SOC AQP-Admins; do
  GROUP_ID="$(az ad group show --group ${group} --query id -o tsv)"
  az ad group member remove --group "${GROUP_ID}" --member-id "${USER_ID}" 2>/dev/null || true
done
```

After removal, capture an evidence snapshot:

```bash
python scripts/identity/list_entra_app_role_assignments.py \
    --format=csv > evidence/entra-after-offboarding-${USER_ID}-$(date +%F).csv
```

## Common pitfalls

| Pitfall | Mitigation |
| --- | --- |
| Adding a user to two conflicting groups | The role union is granted; review with `list_entra_app_role_assignments.py` after every change |
| Group propagation lag | Ask the user to wait 5 minutes between group add and login retry |
| User can't sign in despite group membership | Check Conditional Access "What If" report for the user; CA may be blocking the sign-in |
| Stale group from a previous role | Remove the old group BEFORE adding the new one to keep the audit trail clean |

## Related

- [`concepts/identity/entra-internal-tenant`](../concepts/identity/entra-internal-tenant.md) — pool concept
- [`how-to/entra-terraform-bootstrap`](./entra-terraform-bootstrap.md) — how the groups exist in the first place
- [`how-to/entra-rotate-secrets`](./entra-rotate-secrets.md) — credential rotation
