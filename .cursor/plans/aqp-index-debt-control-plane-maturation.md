# aqp_index debt note — control-plane + admin maturation (Phase 0 + 1)

Per the always-on `.cursor/rules/aqp-index-reflect.mdc` rule, this
note enumerates every qualifying surface touched by the control-plane
+ admin maturation PR. The
[aqp-index-curator](.cursor/agents/aqp-index-curator.md) subagent
should consume this on its next scheduled pass and refresh the
matching `aqp_index/*` pointers.

## Qualifying surfaces changed

### Repo-root governance docs

- `AGENTS.md`
  - Rule 42 wording rewritten — `TerraformRuntime` canonical owner
    moved from `aqp/terraform/runtime.py` to
    `aqp_control_plane/src/aqp_cp/terraform/runtime.py`. The
    in-monolith path stays as a thin HTTP broker gated by
    `AQP_TERRAFORM_USE_CONTROL_PLANE`. The new wording also points
    at the relocated executor path
    (`aqp_cp/terraform/runtime.py::TerraformExecutor`) for the
    `subprocess.run(["terraform", ...])` invariant.

### `.cursor/rules/`

- `.cursor/rules/terraform.mdc` — hard rule 1 repointed at the CP
  location and notes the `AQP_TERRAFORM_USE_CONTROL_PLANE` rollout
  gate.
- `.cursor/rules/identity.mdc` — description + globs expanded to
  cover `aqp_admin/src/aqp_admin/deps/identity.py`,
  `aqp_admin/aqp_admin_ui/src/lib/auth/**/*.{ts,tsx}`, and
  `aqp_platform_core/src/aqp_platform_core/auth/**/*.py`. The
  Entra-primary decision is now an explicit prelude.
- `.cursor/rules/multitenant.mdc` — Hard rule 3 wording updated:
  "Microsoft Entra ID is the platform's PRIMARY IdP" + the
  `default_identity_provider_alias` reference.

### `aqp_platform_core` public surface additions

- `aqp_platform_core/src/aqp_platform_core/runtime/progress.py` (new)
  — `ProgressEmitter`, `NullProgressEmitter`,
  `StructuredLogProgressEmitter`.
- `aqp_platform_core/src/aqp_platform_core/runtime/__init__.py` — re-
  exports the new emitter types.
- `aqp_platform_core/src/aqp_platform_core/auth/__init__.py` —
  `default_identity_provider_alias`, `is_entra_primary`,
  `SUPPORTED_IDENTITY_PROVIDERS`, `M2MTokenBroker`,
  `MsalEntraValidator`, `M2MGrant`, `IdentityProviderShim`.
- `aqp_platform_core/src/aqp_platform_core/auth/providers/`
  (new package) with `protocol.py` + `msal_entra.py`.
- `aqp_platform_core/src/aqp_platform_core/auth/m2m.py` (new) — the
  Entra-primary M2M token broker.
- `aqp_platform_core/src/aqp_platform_core/models/tenancy.py` (new)
  — `TenantNamespaceSpec`, `TenantNamespaceStatus`, `TenantQuotas`,
  `TenantLimitRange`, `TenantPlan`, `NetworkPolicyMode`.
- `aqp_platform_core/src/aqp_platform_core/models/terraform.py`
  (new) — `TerraformStackSpec`, `TerraformRunResult`,
  `TerraformRunKind`, `TerraformRunStatus`, `TerraformStateBackend`.
- `aqp_platform_core/src/aqp_platform_core/providers/protocol.py` —
  ABC extended with `provision_tenant_namespace` and
  `deprovision_tenant_namespace`.
- `aqp_platform_core/src/aqp_platform_core/models/workloads.py` —
  `WorkloadAction` gains `HALT`, `PROVISION_TENANT`,
  `DEPROVISION_TENANT`, `BUILD_IMAGE`, and `TERRAFORM_*` members.

### `aqp_control_plane` public surface additions

- `aqp_control_plane/src/aqp_cp/api/routers/tenants.py` (new) —
  `/manage/tenants/{tenant_id}/provision` + `/render` + `GET` +
  `DELETE`.
- `aqp_control_plane/src/aqp_cp/api/routers/builds.py` (new) —
  `/manage/builds` + WebSocket `/manage/builds/{job_name}/logs/stream`.
- `aqp_control_plane/src/aqp_cp/api/routers/terraform.py` (new) —
  `/manage/terraform/workspaces/{workspace_id}/{plan,apply,destroy,validate}`,
  `/manage/terraform/halt`, `/manage/terraform/halt/status`.
- `aqp_control_plane/src/aqp_cp/api/routers/deployments.py` — added
  WebSocket `/manage/deployments/{service_id}/logs/stream`.
- `aqp_control_plane/src/aqp_cp/api/routers/observability.py` —
  added `/manage/observability/prometheus/query/tenant` and
  `query_range/tenant` (identity-aware PromQL proxy).
- `aqp_control_plane/src/aqp_cp/builders/` (new) — `kaniko.py` +
  `tenant.py` + Jinja `manifests/` package.
- `aqp_control_plane/src/aqp_cp/services/prometheus.py` (new) —
  `PromQLLabelInjector`, `IdentityAwarePrometheusClient`.
- `aqp_control_plane/src/aqp_cp/services/http_audit_sink.py` (new)
  — `HttpAuditSink`, `EnvSecretStore`.
- `aqp_control_plane/src/aqp_cp/terraform/` (new package) —
  `TerraformRuntime`, `TerraformExecutor`,
  `TerraformRequestContext`.
- `aqp_control_plane/src/aqp_cp/providers/kubernetes.py` —
  `KubernetesProvider.provision_tenant_namespace` +
  `deprovision_tenant_namespace`.
- `aqp_control_plane/src/aqp_cp/settings.py` — many new env knobs
  (`AQP_CP_PROMETHEUS_*`, `AQP_CP_KANIKO_*`, `AQP_CP_TERRAFORM_*`,
  `AQP_CP_AUDIT_HTTP_URL`, `AQP_CP_M2M_*`, `AQP_CP_AUTH_PROVIDER`,
  `AQP_CP_ENTRA_TENANT`, `AQP_CP_TENANT_NAMESPACE_PREFIX`).
- `aqp_control_plane/pyproject.toml` — `Jinja2` dependency,
  `observability` extras (`prometheus-api-client`), force-include
  of `aqp_cp/builders/manifests/` into the wheel.

### `aqp_admin` public surface real implementations

- `aqp_admin/src/aqp_admin/settings.py` — full auth + audit + M2M
  fields under one `AdminSettings` model. Env aliases re-mapped to
  per-knob explicit names.
- `aqp_admin/src/aqp_admin/main.py` — rewrote `create_app` to
  register the canonical admin routers (best-effort) and wire
  audit-sink lifecycle hooks.
- `aqp_admin/src/aqp_admin/deps/` (new) — `identity.py` +
  `audit.py` + package `__init__.py`.
- `aqp_admin/src/aqp_admin/audit/` (new) — `sink.py` with
  `AdminAuditEvent`, `AdminAuditSink`, `JsonlAdminAuditSink`,
  `HttpAdminAuditSink`, `LoggingAdminAuditSink`,
  `build_default_audit_sink`.
- `aqp_admin/src/aqp_admin/integrations/` (new) — `broker.py` with
  `ControlPlaneBroker`, `MonolithBroker`, `HaltBroker`,
  `AdminBrokerError`, `EnvSecretStore`.
- `aqp_admin/src/aqp_admin/accounts/{organizations,billing,tenancy}.py`
  — replaced stubs with real brokered implementations.
- `aqp_admin/src/aqp_admin/services/managed.py` — brokered
  `ManagedServiceCatalog`.
- `aqp_admin/src/aqp_admin/providers/stripe.py` — real
  `StripeProvider` that resolves the secret via
  `CredentialResolver` + lazy-imports the SDK.
- `aqp_admin/src/aqp_admin/api/routers/`:
  - `accounts.py` — expanded (org detail, billing summary, invite
    create, Entra-link promotion).
  - `services.py` — real broker call.
  - `tenants.py` (new) — tenant-vending wizard backend.
  - `halt.py` (new) — `POST /admin/halt/all` fan-out.
  - `audit.py` (new) — JSONL tail.
  - `builds.py` (new) — brokered Kaniko submit + status.
  - `runbooks.py` (new) — TipTap runbook upsert + read.
  - `metrics.py` (new) — identity-aware PromQL passthrough.

### `aqp_admin_ui` public surface real implementations

- `aqp_admin/aqp_admin_ui/package.json` — added
  `@azure/msal-browser`, `@auth0/auth0-spa-js`, `@tiptap/react`,
  `@tiptap/starter-kit`.
- `aqp_admin/aqp_admin_ui/src/lib/api.ts` — full typed client for
  the new BFF endpoints + `setBearerProvider` injection.
- `aqp_admin/aqp_admin_ui/src/lib/auth/` (new) — `AuthProvider.tsx`,
  `useAuth.ts`, `useStepUp.ts` with MSAL-primary / Auth0-fallback
  detection.
- `aqp_admin/aqp_admin_ui/src/components/common/` (new) —
  `KillSwitch.tsx`, `ConfirmFrictionDialog.tsx`, `SandboxBadge.tsx`.
- `aqp_admin/aqp_admin_ui/src/components/layout/AdminShell.tsx` —
  expanded nav + topbar with `KillSwitch` mounted.
- `aqp_admin/aqp_admin_ui/src/routes/`:
  - `tenants/new.tsx` (new) — vending wizard.
  - `tenants/detail.tsx` (new) — tenant detail + identity-aware
    PromQL panels.
  - `builds/index.tsx` (new) — submit + recent list.
  - `builds/detail.tsx` (new) — live WS log stream.
  - `runbooks/index.tsx` + `runbooks/editor.tsx` (new) — TipTap
    editor (lazy-loaded).
- `aqp_admin/aqp_admin_ui/src/main.tsx` — wraps the app in
  `AuthProvider` and bridges `getAccessToken` into `adminApi`.
- `aqp_admin/aqp_admin_ui/src/App.tsx` — adds the new routes.

### Auth0 / Terraform IaC bundles

- `auth0/actions/scim-outbound.{js,config.json}` (new) — skeleton
  outbound SCIM Action.
- `aqp_platform/terraform/modules/auth0/scim-outbound/` (new) —
  Terraform module that provisions the Action behind
  `enable_action_binding`.

## New always-on credential expectations

- Admin BFF audit sink writes are best-effort — JSONL by default,
  HTTP via the Entra-primary M2M broker when
  `AQP_ADMIN_AUDIT_SINK=http`.
- Stripe + future billing providers MUST resolve their secrets
  through the `CredentialResolver` chain (the env-store shim in
  `aqp_admin.integrations.broker.EnvSecretStore` is the default).
- Kaniko Job pods MUST get cloud creds via EKS Pod Identity / IRSA
  / Workload Identity Federation. The renderer test asserts the
  manifest does NOT mount cloud-credential Secrets — keep that
  invariant when extending the Kaniko surface.
- The CP-native `TerraformRuntime` honours the kill-switch via a
  filesystem sentinel (`AQP_CP_TERRAFORM_KILL_SWITCH_SECRET_PATH`).
  Mutating actions (apply / destroy) return `status=rejected` when
  the sentinel exists.
- The PromQL rewriter applies a deny list
  (`AQP_CP_PROMETHEUS_DENY_METRICS`); operators with
  `admin:cluster` may opt out per-query via `disable_tenant_filter=true`.

## Suggested aqp_index refresh actions for the curator

1. Refresh `aqp_index/architecture/control-plane.md` (if present)
   to point at the new `aqp_cp/terraform/` + `aqp_cp/builders/`
   sub-packages.
2. Update the SSoT pointer for "where TerraformRuntime lives" —
   `aqp_index/code-indices/runtimes.md`.
3. Add the new `/admin/*` routes + their `manage:tenants`,
   `manage:agents`, `workloads:halt` scope mapping to
   `aqp_index/configurations/scopes.md`.
4. Add `MsalEntraValidator`, `M2MTokenBroker`, `ProgressEmitter`,
   `IdentityAwarePrometheusClient`, `KanikoBuilder` to the
   platform-core / control-plane code indices.
5. Refresh the Entra-primary decision in
   `aqp_index/architecture/identity.md`.

## Follow-ups deliberately deferred to subsequent PRs

- Physically relocate `aqp/terraform/**` into the CP and convert the
  in-monolith call sites to thin brokers (the flag gate is in
  place; the broker shim is the next PR).
- Auth0 outbound SCIM payload bodies — the Action ships in
  skeleton (deployed-but-inactive) form.
- React Flow pipeline composer + JSONForms-driven Terraform editor.
- TipTap collaboration (Hocuspocus / Yjs).
- vCluster / Capsule per-tenant runtimes.
- Per-tenant NATS account isolation.
- Full SOC 2 evidence pipeline + cost-allocation warehouse.
