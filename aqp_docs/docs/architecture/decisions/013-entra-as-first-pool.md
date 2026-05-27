---
title: "ADR-013: Entra ID as the AQP staff first user pool"
sidebar_position: 13
---

# ADR-013: Entra ID as the AQP staff first user pool

- **Status**: Accepted
- **Date**: 2026-05-27
- **Supersedes**: none
- **Superseded by**: none
- **Related rules**: AGENTS rule 27 (identity), 42 (TerraformRuntime),
  44 (EntraTenantLink approval flow), 26 (CredentialResolver)
- **Related ADRs**: [ADR-003 Auth0 zero-trust](003-auth0-zero-trust.md)
  remains valid for B2C / customer-tenant fallback;
  [ADR-005 separated control plane](005-separated-control-plane.md)
  is the host for the new `manage.aqp.fund` MSAL routes.

## Context

The Agentic Quant Platform has historically authenticated AQP staff
through the same Auth0 tenant that serves customer logins. Auth0 has
served well as a B2C identity surface, but for the **internal** staff
pool we need:

1. **Centralised MFA + Conditional Access**. Staff already authenticate
   to Microsoft 365 daily through the corporate Entra tenant. CA
   policies (block risky sign-ins, named-location MFA, FIDO2 hardware
   key requirements for admins) are enforced by the IT / Security team
   in one place. Replicating those controls in Auth0 doubles the
   surface area.
2. **Audit centralisation**. The corporate SIEM already ingests Entra
   sign-in logs via the existing log stream. Auth0 audit data has to
   be exported separately and reconciled.
3. **Group-driven authorisation**. New hires onboard via a single
   HR-side group action; the Entra group's app-role mapping
   automatically grants the right AQP scopes. The Auth0 path required
   manual role assignment in the Auth0 dashboard.
4. **No client secrets in CI**. GitHub Actions OIDC + federated
   credentials replace the old `AZURE_CLIENT_SECRET` repo secret.
5. **Customer separation**. The AQP staff Entra tenant is independent
   of every customer Entra tenant. Customer tenants continue to flow
   through the existing `EntraTenantLink` B2B approval wizard
   (AGENTS rule 44) — they do NOT land in the staff tenant.

The runtime support for Entra has been in place since the Phase 4
service-mesh rollout (`aqp/auth/providers/msal_entra.py`); this ADR
formalises the *first user pool* designation and brings the Entra
configuration under Terraform control.

## Decision

1. **The AQP staff Microsoft Entra ID tenant is the first user pool
   for `manage.aqp.fund`**. Tokens whose `iss` matches the AQP staff
   tenant are routed through `MsalEntraIdentityProvider` before any
   other provider in the chain.
2. **Auth0 stays as the customer-facing B2C pool** and as the
   degraded-mode fallback for staff (e.g. if the Entra side has an
   incident).
3. **Every Entra resource is under Terraform control** through the
   new `aqp_entra_directory` module: 3 app registrations + 7 directory
   groups + 7 app roles + group → role assignments + named locations
   + GitHub Actions OIDC federated credentials.
4. **Conditional Access policies remain manually authored** because P2
   licensing requires Security-team review on every policy change. The
   Terraform module records policy display names as documentation; a
   smoke-test helper queries Microsoft Graph at apply time to confirm
   each named policy exists.
5. **Apply path is `TerraformRuntime` only** (rule 42). Plan-only on
   PR; apply on push to `main` through `aqp deploy`.
6. **Federated credentials replace static client secrets in CI**. The
   `aqp-ci-github` app's federated credentials are per-environment +
   per-branch — wildcards are rejected at plan time.

## Alternatives considered

### A. Keep Auth0 as the staff pool

Pros:
- Zero migration effort.
- Single identity surface for both staff + customers.

Cons:
- Doubles the MFA + CA enforcement surface.
- Splits audit logs across two systems (Auth0 + corporate SIEM).
- Manual role assignment in the Auth0 dashboard for every new hire.
- Static client secrets in CI.

**Rejected**: the operational + audit overhead outweighs the
zero-migration win.

### B. Migrate ALL identity (staff + customers) to Entra

Pros:
- Single user pool overall.
- Strongest audit centralisation.

Cons:
- Customer tenants are operated by their own admins; we can't unify
  them into a single tenant we control.
- B2C scenarios (e.g. self-service trial signups) are awkward in
  enterprise Entra; Auth0 + the existing B2C surface is the right
  tool.
- Migration cost: every existing Auth0 customer connection would need
  to be re-issued in Entra B2C (different protocol, different SDK).

**Rejected**: the staff vs customer split is the right granularity.

### C. Keep Entra resources in the Azure Portal (no Terraform)

Pros:
- Lower friction for ad-hoc adjustments.
- No Terraform learning curve for IT staff.

Cons:
- No reviewable diff for changes.
- No `terraform_runs` audit row for compliance.
- No federated-credential automation; CI keeps a static secret.
- Drift between dev / prod tenants becomes hard to detect.

**Rejected**: clickops on identity infrastructure violates AGENTS rule
42 in spirit (audit-first, every change reviewed).

## Consequences

### Positive

- One MFA + CA enforcement surface for staff, owned by Security.
- Audit logs land in the corporate SIEM via the existing log stream.
- New-hire onboarding is one HR-side group add.
- CI authenticates to Azure with no stored secrets.
- Customer Entra tenants flow through the existing B2B path; the
  internal pool doesn't bleed into customer scope.
- The `aqp_entra_directory` module is reviewable; every change gets a
  PR + plan diff.

### Negative

- Two identity providers to keep healthy (Entra + Auth0). Mitigated
  by `select_provider_for_token` routing — the right provider is
  picked per-request rather than per-deploy.
- Bootstrap window has a temporary client secret (Phase 0/1 of the
  rollout plan); retired in Phase 5.
- CA policies remain a manual surface — the Terraform module can
  reference them but cannot create them. Mitigated by the smoke-test
  helper that confirms required policies exist before exposure.
- Group membership is intentionally outside Terraform. HR + Security
  own membership; the audit path comes from the Entra audit log
  rather than `terraform_runs`.

### Risks + mitigations

| Risk | Mitigation |
| --- | --- |
| Tenant lockout (every admin's account gets MFA-locked) | TWO break-glass accounts excluded from CA policies (rollout plan §4 + `entra-rotate-secrets` runbook). |
| Group → role mapping mistake grants over-privileged access | `terraform_runs` audit + the daily Prometheus alert on `entra_role_assignment_changes_total`. |
| Federated-credential subject too broad | Per-environment / per-branch subjects; module rejects wildcards at plan time. |
| Customer-tenant tokens routed to MSAL-internal | `select_provider_for_token` checks the `iss` claim against `auth_msal_internal_tenant_id`; mismatch falls through to Auth0. Unit tested. |

## Implementation pointers

- Long-form rollout plan:
  [`docs/plans/entra-internal-tenant-rollout.md`](pathname:///docs/plans/entra-internal-tenant-rollout.md)
- Concepts:
  [`concepts/identity/entra-internal-tenant`](../../concepts/identity/entra-internal-tenant.md)
- Bootstrap runbook:
  [`how-to/entra-terraform-bootstrap`](../../how-to/entra-terraform-bootstrap.md)
- Onboarding runbook:
  [`how-to/entra-onboard-new-staff`](../../how-to/entra-onboard-new-staff.md)
- Secret-rotation runbook:
  [`how-to/entra-rotate-secrets`](../../how-to/entra-rotate-secrets.md)
- Module:
  [`aqp_platform/terraform/modules/aqp_entra_directory/`](pathname:///aqp_platform/terraform/modules/aqp_entra_directory/README.md)
- Provider runtime: `aqp/auth/providers/msal_entra.py`
- Provider chain selector: `aqp/auth/providers/__init__.py::select_provider_for_token`
