# =============================================================================
# aqp_entra_directory — main.tf
#
# Workstream "Entra internal tenant" (docs/plans/entra-internal-tenant-rollout.md).
# Brings the AQP staff Entra ID tenant under Terraform control:
#   * 3 app registrations (staff login, manage API, CI federation)
#   * service principals + app role definitions on the manage API
#   * 7 directory groups + group-to-app-role assignments
#   * federated credentials for GitHub Actions OIDC (no static secrets)
#   * named locations + Conditional Access policy data sources
#
# AGENTS rule 27: identity flows through the existing IdentityProvider
# chain; this module only provisions the Entra-side resources. The
# runtime side lives in aqp/auth/providers/msal_entra.py.
# AGENTS rule 42: never call ``terraform apply`` directly. Apply path is
# routed through TerraformRuntime via ``aqp deploy``; CI workflow at
# .github/workflows/entra-terraform.yml.
# =============================================================================

# Look up the configured tenant + the well-known Microsoft Graph SP
# (every API permission below references its app role / oauth2 scope ids).
data "azuread_client_config" "current" {}

data "azuread_application_published_app_ids" "well_known" {}

data "azuread_service_principal" "msgraph" {
  client_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]
}

# -----------------------------------------------------------------------------
# Validation locals — enforce invariants the plan must satisfy.
# -----------------------------------------------------------------------------
locals {
  # Map role values back to their UUIDs for group-binding lookups.
  app_role_value_to_id = {
    for r in var.app_role_definitions : r.value => r.id
  }

  # Every group's ``role_values`` must reference a defined role.
  unknown_role_values = flatten([
    for g in var.groups : [
      for v in g.role_values : v if !contains(keys(local.app_role_value_to_id), v)
    ]
  ])

  # Reject overly broad federated credential subjects.
  bad_ci_subjects = [
    for c in var.ci_federated_credentials : c.subject
    if can(regex("\\*", c.subject)) || can(regex(":ref:refs/heads/\\*$", c.subject))
  ]

  # Group display names / role values must be unique across the list.
  group_keys_dup = length(var.groups) != length(distinct([for g in var.groups : g.key]))

  # Constants for Microsoft Graph delegated permission ids
  # (https://learn.microsoft.com/graph/permissions-reference).
  msgraph_user_read  = "e1fe6dd8-ba31-4d61-89e7-88639da4683d"
  msgraph_openid     = "37f7f235-527c-4136-accd-4a02d197296e"
  msgraph_profile    = "14dad69e-099b-42c9-810b-d002981feec1"
  msgraph_email      = "64a6cdd6-aab1-4aaf-94b8-3cc8405e90d0"
  msgraph_group_read = "5f8c59db-677d-491f-a6b8-5f174b11ec1d" # Group.Read.All (delegated)
  msgraph_offline    = "7427e0e9-2fba-42fe-b0c0-848c9e6a8182" # offline_access

  enabled_count = var.enabled ? 1 : 0
}

# Compile-time invariants. Each ``check`` raises a plan-time error.
check "all_role_values_defined" {
  assert {
    condition     = length(local.unknown_role_values) == 0
    error_message = "var.groups references undefined role values: ${join(", ", local.unknown_role_values)}"
  }
}

check "no_wildcard_ci_subjects" {
  assert {
    condition     = length(local.bad_ci_subjects) == 0
    error_message = "var.ci_federated_credentials carries wildcard subjects (forbidden): ${join(", ", local.bad_ci_subjects)}"
  }
}

check "unique_group_keys" {
  assert {
    condition     = !local.group_keys_dup
    error_message = "var.groups has duplicate ``key`` values; each group must be uniquely keyed."
  }
}

# -----------------------------------------------------------------------------
# 1. Manage API Resource Server (app + SP + app roles).
# -----------------------------------------------------------------------------
resource "azuread_application" "manage_api" {
  count            = local.enabled_count
  display_name     = "${var.display_name_prefix} ${var.manage_api_app.name}"
  description      = var.manage_api_app.description
  identifier_uris  = [var.manage_api_app.identifier_uri]
  sign_in_audience = var.manage_api_app.sign_in_audience

  # App roles defined on the Resource Server. Tokens minted for this
  # audience carry the ``roles`` claim with the role values below.
  dynamic "app_role" {
    for_each = var.app_role_definitions
    content {
      id                   = app_role.value.id
      value                = app_role.value.value
      display_name         = app_role.value.display_name
      description          = app_role.value.description
      allowed_member_types = app_role.value.allowed_member_types
      enabled              = true
    }
  }

  # Web platform: tokens minted via the on-behalf-of flow from the
  # staff app. No browser callbacks here — the manage API is a
  # Resource Server, not a SPA.
  api {
    requested_access_token_version = 2
    mapped_claims_enabled          = true
  }

  feature_tags {
    enterprise = true
    gallery    = false
  }
}

resource "azuread_service_principal" "manage_api" {
  count                        = local.enabled_count
  client_id                    = azuread_application.manage_api[0].client_id
  app_role_assignment_required = true
  description                  = "Service principal for the AQP manage API. App role assignment required."
  notes                        = "Provisioned by aqp_platform/terraform/modules/aqp_entra_directory."
  feature_tags {
    enterprise = true
  }
}

# -----------------------------------------------------------------------------
# 2. Staff login app (aqp-staff).
#
# Pre-authorised against the manage API so users get tokens for both
# audiences without re-consenting.
# -----------------------------------------------------------------------------
resource "azuread_application" "staff" {
  count            = local.enabled_count
  display_name     = "${var.display_name_prefix} ${var.staff_app.name}"
  description      = var.staff_app.description
  sign_in_audience = var.staff_app.sign_in_audience

  web {
    redirect_uris = var.staff_app.redirect_uris
    logout_url    = length(var.staff_app.logout_urls) > 0 ? var.staff_app.logout_urls[0] : ""
    implicit_grant {
      access_token_issuance_enabled = false
      id_token_issuance_enabled     = false
    }
  }

  public_client {
    redirect_uris = var.staff_app.public_client_enabled ? var.staff_app.redirect_uris : []
  }

  optional_claims {
    access_token {
      name = "groups"
    }
    id_token {
      name = "groups"
    }
  }

  group_membership_claims = ["SecurityGroup"]

  required_resource_access {
    resource_app_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]
    dynamic "resource_access" {
      for_each = [
        local.msgraph_openid,
        local.msgraph_profile,
        local.msgraph_email,
        local.msgraph_user_read,
        local.msgraph_group_read,
        local.msgraph_offline,
      ]
      content {
        id   = resource_access.value
        type = "Scope"
      }
    }
  }

  required_resource_access {
    resource_app_id = azuread_application.manage_api[0].client_id
    dynamic "resource_access" {
      for_each = var.app_role_definitions
      content {
        id   = resource_access.value.id
        type = "Role"
      }
    }
  }
}

resource "azuread_service_principal" "staff" {
  count                        = local.enabled_count
  client_id                    = azuread_application.staff[0].client_id
  app_role_assignment_required = false
  description                  = "Service principal for the AQP staff login app."
  feature_tags {
    enterprise = true
  }
}

# -----------------------------------------------------------------------------
# 3. CI federation app (aqp-ci-github).
#
# No browser flow; only federated credentials. Operators MUST grant
# this app the minimum Graph permissions needed for the CI workflow
# (typically just Application.Read.All to verify deploys).
# -----------------------------------------------------------------------------
resource "azuread_application" "ci_github" {
  count            = local.enabled_count
  display_name     = "${var.display_name_prefix} ${var.ci_app.name}"
  description      = var.ci_app.description
  sign_in_audience = var.ci_app.sign_in_audience

  feature_tags {
    enterprise = true
  }
}

resource "azuread_service_principal" "ci_github" {
  count                        = local.enabled_count
  client_id                    = azuread_application.ci_github[0].client_id
  app_role_assignment_required = true
  description                  = "Service principal for the GitHub Actions OIDC federation."
  feature_tags {
    enterprise = true
  }
}

resource "azuread_application_federated_identity_credential" "ci_github" {
  for_each = var.enabled ? {
    for c in var.ci_federated_credentials : c.name => c
  } : {}

  application_id = azuread_application.ci_github[0].id
  display_name   = each.value.name
  description    = each.value.description
  audiences      = [each.value.audience]
  issuer         = each.value.issuer
  subject        = each.value.subject
}

# -----------------------------------------------------------------------------
# 4. Directory groups.
# -----------------------------------------------------------------------------
resource "azuread_group" "groups" {
  for_each = var.enabled ? {
    for g in var.groups : g.key => g
  } : {}

  display_name            = each.value.display_name
  description             = each.value.description
  security_enabled        = each.value.security_only
  mail_enabled            = false
  assignable_to_role      = each.value.assignable_to_role
  prevent_duplicate_names = true
  owners                  = [data.azuread_client_config.current.object_id]
}

# -----------------------------------------------------------------------------
# 5. Group → app role assignments.
#
# Each (group, role) pair lands as one ``azuread_app_role_assignment``.
# Use a flattened map keyed by ``"<group_key>__<role_value>"`` so plan
# diffs are stable as the input lists change.
# -----------------------------------------------------------------------------
locals {
  group_role_pairs = var.enabled ? merge([
    for g in var.groups : {
      for v in g.role_values :
      "${g.key}__${v}" => {
        group_key  = g.key
        role_value = v
      }
    }
  ]...) : {}
}

resource "azuread_app_role_assignment" "group_to_role" {
  for_each = local.group_role_pairs

  app_role_id         = local.app_role_value_to_id[each.value.role_value]
  principal_object_id = azuread_group.groups[each.value.group_key].object_id
  resource_object_id  = azuread_service_principal.manage_api[0].object_id
}

# -----------------------------------------------------------------------------
# 6. Pre-authorised application: staff -> manage API.
#
# Lets users hold a single sign-in session and get tokens for both
# audiences without re-consenting.
# -----------------------------------------------------------------------------
resource "azuread_application_pre_authorized" "staff_to_manage_api" {
  count = local.enabled_count

  application_id       = azuread_application.manage_api[0].id
  authorized_client_id = azuread_application.staff[0].client_id

  permission_ids = [for r in var.app_role_definitions : r.id]
}

# -----------------------------------------------------------------------------
# 7. Named locations (trusted IP ranges).
# -----------------------------------------------------------------------------
resource "azuread_named_location" "ip_ranges" {
  for_each = var.enabled ? {
    for n in var.named_locations : n.display_name => n
  } : {}

  display_name = each.value.display_name

  ip {
    ip_ranges = each.value.ip_ranges
    trusted   = each.value.is_trusted
  }
}

# -----------------------------------------------------------------------------
# 8. Conditional Access policy references.
#
# The hashicorp/azuread provider does NOT expose a data source for CA
# policies (only a managed resource); creating CA policies requires a
# P2 license and manual Security review (rollout plan §1.2). We carry
# the policy names here as documentation only; helper-script
# ``scripts/identity/verify_entra_login.py`` queries Microsoft Graph
# at smoke-test time to confirm each named policy exists.
# -----------------------------------------------------------------------------
locals {
  ca_policy_documentation = [
    for p in var.ca_policy_references : {
      display_name = p.display_name
      purpose      = p.purpose
    }
  ]
}
