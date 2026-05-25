# aqp_index debt note — admin settings + cloud onboarding

Per `.cursor/rules/aqp-index-reflect.mdc`, this change touched qualifying
public surfaces under `aqp_admin/` and requires a curator refresh on the next
`aqp-index-curator` pass.

## Changed qualifying surfaces

- `aqp_admin/src/aqp_admin/api/routers/settings.py` (new)
  - Added `/admin/settings/*` endpoints for framework config read/patch and
    cloud onboarding actions (AWS/Azure/GCP provider connect + Cloudflare
    connect/health).
- `aqp_admin/src/aqp_admin/integrations/broker.py`
  - Added control-plane config + telemetry broker methods and monolith
    Terraform/Cloudflare methods used by the new settings router.
- `aqp_admin/src/aqp_admin/main.py`
  - Registered the settings router and root endpoint pointer.
- `aqp_admin/aqp_admin_ui/src/lib/api.ts`
  - Added typed DTOs + client methods for settings/cloud status and connect
    mutations.
- `aqp_admin/aqp_admin_ui/src/routes/settings/index.tsx` (new route)
  - Added settings page with framework editor + cloud onboarding panels.
- `aqp_admin/aqp_admin_ui/src/components/settings/` (new)
  - Added `FrameworkSettingsPanel`, `CloudProviderWizard`, `CloudflareWizard`.
- `aqp_admin/aqp_admin_ui/src/components/layout/AdminShell.tsx`
  - Added Settings nav entry.
- `aqp_admin/aqp_admin_ui/src/App.tsx`
  - Added `/settings` route registration.

## aqp_index refresh targets

- `aqp_index/code-indices/aqp_admin.md` (or equivalent admin code-index file)
- `aqp_index/architecture/control-plane.md` (admin BFF broker touchpoints)
- `aqp_index/configurations/scopes.md` (new admin.settings.* actions/scope usage)
- `aqp_index/project-index.md` (new settings UI route + backend router surface)

## One-line curator summary

Add admin settings/cloud onboarding surfaces (new `/admin/settings/*` backend
router, new `/settings` UI route, and broker/API client expansions) to
`aqp_index` pointers and code indices.
