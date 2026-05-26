# ADR 006: aqp_admin overhaul (multi-cloud control plane)

- **Status:** Proposed
- **Date:** 2026-05-25
- **Supersedes:** none (extends ADR 002 single-container client; the
  Solara legacy half is deprecated by this overhaul)
- **Superseded by:** none

## Context

The aqp_admin internal admin surface predates the overhaul:

- Backend was already a stateless FastAPI BFF brokering audit-first
  to `aqp_control_plane` and the AQP monolith.
- Frontend was a Vite + React Router SPA at `aqp_admin/aqp_admin_ui/`.
- Six modules from the blueprint were missing: secrets-manager,
  lineage-explorer, model-registry, paper-trading-control,
  rbac-admin, account-mode-switcher.
- Multi-account AWS topology was not provisioned.
- CI used `KUBECONFIG_*` base64 secrets instead of GitHub Actions
  OIDC.
- Only the bot fleet had ArgoCD; the main stack was kubectl-push.
- No S3 WORM mirror for `security_audit_events`.

## Decision

### Frontend: migrate to Next.js 15 App Router.

Even though `aqp_client/` (the canonical Vite operator UI) and
`aqp_ui/` (the customer-facing PaaS) keep their existing
frameworks, the admin surface migrates to Next.js because:

- Server Components reduce the bundle on read-heavy admin pages.
- Server Actions remove API-route boilerplate for mutations.
- File-system routing maps cleanly onto the sidebar information
  architecture (one folder per module).
- Middleware-based auth with one-shot RFC 9470 step-up retries
  composes better than the Vite + React Router pattern.

The legacy `aqp_admin_ui/` stays deployable behind a feature flag
for a 30-day rollback window during the cutover. The new Next.js
app lives at `aqp_admin/frontend/`.

### Backend: extend, don't rewrite.

The existing six routers are kept. Six new module routers are
added under the established audit-first / M2M-broker /
`require_admin_scope` pattern. Step-up MFA per AGENTS rule 52 is
attached to every new mutating endpoint.

### RBAC: stay on the existing 4-role lattice.

The blueprint suggested Casbin. We reject that — AQP's canonical
RBAC is the
`aqp_platform_core.auth.rbac` 4-role lattice plus the existing
`Membership` table. Adding Casbin would create a parallel policy
source-of-truth that fragments rule 27. The new
`/admin/rbac/*` router builds on `expand_role` and the existing
`require_scope` / `require_membership` deps.

### Multi-account AWS: code now, apply later.

A new top-level `infrastructure/` directory ships the full module
library (landing-zone, account, vpc, eks-cluster, eks-node-groups,
karpenter-bootstrap, ecr-repositories, rds-postgres, s3-data-lake,
msk-kafka, airflow, eso-bootstrap, argocd-bootstrap,
observability-stack, iam-irsa-roles, route53-zones,
acm-certificates, acm-pca, github-oidc, codepipeline, codebuild,
codeartifact) plus per-environment compositions. Every
composition assumes-role into a workload account from
`shared-services` with `external_id`. Cloud-side `terraform
apply` is deferred to operator hands; the PR ships the code.

### CI/CD: GitHub OIDC + SLSA L3 + Cosign keyless.

`.github/actions/{aws-oidc-assume,build-sign-push,slsa-provenance,
kubectl-via-irsa}` composite actions; new workflows
`pr-validate.yml`, `build-publish.yml`, `argocd-trigger.yml`,
`terraform-pipeline.yml`, `ml-pipeline.yml`,
`paper-config-validate.yml`, `alembic-immutability.yml`. Renovate
is wired with auto-merge to `main` only on minor + patch updates.

### Observability + cost.

Linkerd (chosen over Istio Ambient + App Mesh because of the
~6x lower proxy memory and ~10x lower p99 latency overhead) is
the service mesh; Falco + Velero + Kubecost ship as Helm-chart
wrappers. Karpenter v1 self-managed (NOT EKS Auto Mode) so the
NodePool specs are recorded under
`terraform_stack_spec_versions`.

### Audit WORM.

`aqp/tasks/audit_log_export_tasks.py::export_audit_log_window`
exports `security_audit_events` + `audit_log` nightly to
`s3://aqp-audit-archive-${ACCOUNT_ID}/` with
`ObjectLockMode=COMPLIANCE` + 7-year retention per FINRA Rule
4511 + SEC Rule 17a-4(f)(2)(i)(B).

### IdP support.

Two new `IdentityProvider` subclasses ship under
`aqp/auth/providers/`:

- `aws_iam_identity_center.py`
- `aws_cognito.py`

Both subclass `GenericOidcProvider` and auto-register through
`IdentityProviderMeta`. IAM Identity Center is the recommended IdP
for multi-account; Cognito is the documented fallback for the
single-account path.

## Consequences

- The 6 missing modules ship with full audit-first wiring +
  step-up MFA + WS multiplexing.
- Frontend bundles get smaller; SSR'd admin pages enable better
  caching.
- Multi-account topology is one `terraform apply` away.
- CI gains SLSA L3 attestations + Cosign keyless verification.
- Audit ledger is FINRA-compliant via WORM mirroring.
- The `aqp_admin_ui/` Vite tree adds maintenance debt for the
  duration of the rollback window. Cleanup PR scheduled
  after 30-day burn-in.
- The legacy `aqp/ui/` Solara dashboard remains in place; a
  separate `aqp_admin-overhaul-cleanup` PR handles its removal +
  the FastAPI/Starlette unpin.
