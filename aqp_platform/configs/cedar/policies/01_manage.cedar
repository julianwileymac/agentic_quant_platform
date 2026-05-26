// =============================================================================
// Generic /manage/* policies — secrets, builds, terraform, tenants.
//
// Phase 4 §7.3 + §7.5 (RESTRUCTURING_PLAN.md). Cedar runs ALONGSIDE
// Pomerium's per-route policy gate (§7.5); these policies enforce
// fine-grained per-action checks that Pomerium's coarse-grained
// route ACLs can't express.
// =============================================================================

// ------------------------------------------------------------------
// 1. Secret rotation requires the `manage:secrets` scope AND an
//    explicit `secret_admin` role. The scope gate is also enforced
//    by `require_scope` upstream; Cedar adds the role check.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"rotate_secret",
  resource is Secret
)
when {
  principal has roles
  && principal.roles.contains("secret_admin")
  && principal has scopes
  && principal.scopes.contains("manage:secrets")
};

// ------------------------------------------------------------------
// 2. Image builds via Kaniko (Phase 1 of the control-plane
//    maturation) require `manage:builds` AND the build target's
//    project must match the principal's org.
// ------------------------------------------------------------------
permit (
  principal,
  action == Action::"build_image",
  resource is Build
)
when {
  principal has scopes
  && principal.scopes.contains("manage:builds")
};

// ------------------------------------------------------------------
// 3. Terraform plan / apply / destroy gated by tier:
//      shared-std    — `terraform_operator` role
//      shared-prem   — `terraform_operator` + matching org_id
//      silo-reg      — `terraform_admin` (more privileged)
// ------------------------------------------------------------------
permit (
  principal,
  action in [
    Action::"terraform_plan",
    Action::"terraform_apply",
    Action::"terraform_refresh"
  ],
  resource is TerraformStack
)
when {
  principal has roles
  && (principal.roles.contains("terraform_operator")
      || principal.roles.contains("terraform_admin"))
};

permit (
  principal,
  action == Action::"terraform_destroy",
  resource is TerraformStack
)
when {
  principal has roles
  && principal.roles.contains("terraform_admin")
};

// ------------------------------------------------------------------
// 4. Tenant namespace provisioning — admins only.
// ------------------------------------------------------------------
permit (
  principal,
  action in [
    Action::"provision_tenant",
    Action::"deprovision_tenant"
  ],
  resource is Tenant
)
when {
  principal has roles
  && (principal.roles.contains("tenant_admin")
      || principal.roles.contains("platform_admin"))
};
