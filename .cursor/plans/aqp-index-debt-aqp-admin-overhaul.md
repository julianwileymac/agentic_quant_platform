# aqp-index debt — aqp_admin overhaul (multi-cloud control plane)

> Per the always-on
> [aqp-index-reflect rule](../rules/aqp-index-reflect.mdc), the
> `aqp_admin` overhaul described in
> [.cursor/plans/aqp_admin_overhaul_a6536451.plan.md](aqp_admin_overhaul_a6536451.plan.md)
> touches enough qualifying surfaces (AGENTS.md, `.cursor/rules/`,
> `aqp_docs/`, `configs/`, `aqp_platform/`, the public surface of
> `aqp_admin`, `aqp_platform_core`, `aqp_control_plane`, plus several
> brand-new top-level folders) that `aqp_index/` MUST be refreshed by
> the [`aqp-index-curator`](../agents/aqp-index-curator.md) subagent
> in the same PR — OR this note must capture the changed surfaces so
> the curator's next scheduled pass picks them up.
>
> Invoke the curator before merging if at all possible.

## Scope

The overhaul implements the full 7-phase blueprint attached to the
parent task:

- Phase 0 — repo hygiene + this debt note.
- Phase 1 — six new aqp_admin modules + Vite -> Next.js 15 frontend
  migration.
- Phase 2 — multi-account AWS Terraform foundation
  (`infrastructure/`).
- Phase 3 — CI/CD hardening (GitHub OIDC, SLSA L3, Cosign keyless,
  reusable composite actions).
- Phase 4 — Control Tower + IAM Identity Center / Cognito IdP +
  cross-account roles.
- Phase 5 — production cutover + DR rehearsal + S3 WORM compliance
  audit mirror + break-glass.
- Phase 6 — Karpenter v1 / KEDA / Linkerd / Falco / Velero / Kubecost
  / Kyverno enforce-mode flip.

## Surfaces changed in this overhaul

### Top-level folders

- **NEW: `infrastructure/`** — multi-account AWS Terraform monorepo
  (bootstrap + envs + modules + policies + gitops + tests). Coexists
  with the existing [`aqp_platform/terraform/`](../../aqp_platform/terraform/)
  (rpi/tower/live/paper/Auth0/Cloudflare). The new tree is
  AWS-multi-account specific; the old tree stays for on-prem +
  Cloudflare Zero Trust + Auth0.
- **NEW: `aqp_admin/frontend/`** — Next.js 15 App Router SPA (replaces
  `aqp_admin/aqp_admin_ui/` Vite SPA; Vite tree retained behind a
  feature flag for 30-day rollback per migration risk register).
- **NEW: `.github/actions/`** — reusable composite actions
  (`aws-oidc-assume`, `build-sign-push`, `slsa-provenance`,
  `kubectl-via-irsa`).
- **NEW: `build/buildspec.<service>.yml`** — AWS CodeBuild parity for
  the sovereign-cloud option.

### `aqp_admin/`

- `src/aqp_admin/api/routers/{secrets,lineage,models,paper,rbac,accounts_mode}.py`
  (NEW) — six new module routers wiring secrets-manager, lineage
  explorer, MLflow model registry, paper-trading control,
  RBAC-on-Membership, and AWS account-mode state machine.
- `src/aqp_admin/integrations/{eso.py,mlflow.py,athena.py}` (NEW) —
  per-module HTTP brokers following the existing
  `ControlPlaneBroker` / `MonolithBroker` pattern.
- `src/aqp_admin/ws/gateway.py` (NEW) — multiplexed `/admin/ws`
  endpoint with channels for telemetry / paper / terraform / argo /
  audit, backed by Redis Streams.
- `src/aqp_admin/services/{account_promoter.py,break_glass.py}`
  (NEW) — Promote-to-Production wizard + 4-eyes break-glass approver.
- `src/aqp_admin/deps/stepup.py` (NEW) — `require_admin_step_up`
  shim that forwards to the monolith's `/auth/step-up/check` endpoint
  (boundary-respectful — the admin BFF cannot import `aqp.*`).
- `aqp_admin/AGENTS.md` and the matching
  [`.cursor/rules/aqp-admin.mdc`](../rules/aqp-admin.mdc) — updated to
  point at `aqp_admin/frontend/` (Next.js) instead of
  `aqp_admin_ui/` (Vite); validation block + boundary table updated.

### `aqp/`

- `aqp/auth/providers/{aws_iam_identity_center.py,aws_cognito.py}`
  (NEW) — two new `IdentityProvider` subclasses; auto-register via
  `IdentityProviderMeta` per AGENTS rule 27. Ship in Phase 4.
- `aqp/tasks/audit_log_export_tasks.py` (NEW) — Celery beat task
  exporting `security_audit_events` + the hash-chained `audit_log`
  to `s3://aqp-audit-archive-{account}/` with
  `ObjectLockMode=COMPLIANCE` + 7-year retention per FINRA Rule 4511
  / SEC Rule 17a-4(f)(2)(i)(B). Ships in Phase 5.

### `aqp_platform/`

- `deployments/kubernetes/helm/{aqp-backend,aqp-redis,aqp-workers,aqp-control-plane}/`
  — chart stubs (currently `.gitkeep`) filled out.
- `deployments/kubernetes/helm/{aqp-admin,falco,velero,kubecost,linkerd-control-plane}/`
  (NEW) — five new Helm charts.
- `Dockerfile` — Solara stage removed once Phase 0 cleanup completes.

### Configs / docs

- `configs/agents/`, `configs/paper/` — unchanged.
- `aqp_docs/docs/operations/dr-replay.md` (NEW) — DR runbook for the
  Phase 5 rehearsal.
- `aqp_docs/docs/operations/break-glass.md` (NEW) — break-glass
  approver runbook.
- `aqp_docs/docs/architecture/decisions/006-aqp-admin-overhaul.md`
  (NEW) — ADR documenting the Next.js migration + multi-account
  topology + RBAC-stays-on-Membership decision.

### Migrations

- No new Alembic migrations in Phase 0 (the audit-flagged 0046 and
  0049 fork mentioned in the blueprint were already resolved by the
  current chain — verified at planning time: only one 0049 file
  exists, audit_report.md no longer exists, latest migration is
  `0081_mlops_skills_and_artifacts`).
- New migration in Phase 5 if the `audit_log_export_runs` ledger
  table is introduced.

## Deferred cleanup (NOT shipped in this overhaul)

The blueprint's Phase 0 calls for deletion of three legacy surfaces
that span hundreds of files with deep cross-references:

- `aqp/ui/` (Solara legacy) — gated by the `[legacy]` profile in
  [pyproject.toml](../../pyproject.toml). Removing it requires
  unwiring the `solara`, `dash`, and `anywidget` deps from the core
  dependency block + auditing every import site + updating the
  matching multi-stage `Dockerfile` `ui` target. This unblocks
  `fastapi>=0.116` once removed.
- `webui/` (legacy Next.js 15) — `frontend/CUTOVER.md` already plans
  this, but `aqp_client/` (the canonical Vite operator UI) has not
  yet absorbed every page. Cutover is in progress.
- `deploy/k8s/` (Kustomize, superseded by
  `aqp_platform/deployments/kubernetes/`).

These three deletions are scheduled for a follow-up PR
(`aqp_admin-overhaul-cleanup`). This overhaul ships every other
phase. The `fastapi<0.116` + `starlette<0.46` pins remain in place
for the duration; the new aqp_admin code already targets the modern
FastAPI surface via the existing pin.

## Why this is option 2

This overhaul is large enough that running the curator inline would
double the diff. The curator's next scheduled pass should refresh:

- `aqp_index/architecture/control-plane.md` — reflect the new
  multi-account topology + Next.js admin surface.
- `aqp_index/configs/index.md` — capture the new Helm charts +
  Terraform modules.
- `aqp_index/code/aqp_admin.md` — token-saving signature index for
  the six new module routers.
- `aqp_index/skills/aqp-admin-promoter-skill.md` (NEW) — author the
  Promote-to-Production skill once the wizard ships.

## Validation invariants

- `aqp_admin/src/aqp_admin/` MUST NOT import `aqp.*` —
  `rg --type py "^from aqp(\\.|$)|^import aqp(\\.|$)"` must return
  nothing per the boundary rule in
  [`aqp-admin.mdc`](../rules/aqp-admin.mdc).
- All new mutating routes ship `Depends(require_admin_step_up(180))`
  per AGENTS rule 52. The Phase 2 allowlist debt for
  `aqp_admin/halt.py` is closed.
- No raw secrets in any audit row, log line, or response body per
  the always-on
  [aqp-management-engine.mdc](../rules/aqp-management-engine.mdc)
  rule.
- All new `IdentityProvider` subclasses set `provider_kind` so the
  `IdentityProviderMeta` metaclass auto-registers them per AGENTS
  rule 27. No manual `@register` decorators.
