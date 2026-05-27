# =============================================================================
# aqp_entra_directory — variables
#
# Inputs the operator/CI provides. Production tfvars live in
# aqp_platform/terraform/environments/wiley-tech/terraform.tfvars
# (gitignored except for the .example template). Every secret-bearing
# input MUST come from CredentialResolver / Vault — NEVER hard-coded.
# =============================================================================

variable "enabled" {
  type        = bool
  default     = false
  description = <<EOT
Master switch. When false, every resource in this module is disabled.
Keep false until the AQP staff Entra tenant is bootstrapped and the
Phase 1 plan-only review has completed (see
docs/plans/entra-internal-tenant-rollout.md §3.2).
EOT
}

# -----------------------------------------------------------------------------
# Tenant + branding
# -----------------------------------------------------------------------------
variable "tenant_id" {
  type        = string
  description = <<EOT
The Entra (Azure AD) tenant id this module manages. Looks like
``00000000-0000-0000-0000-000000000000``. Operators set this via
TF_VAR_tenant_id sourced from Vault; never commit a tenant id to
the .tfvars file.
EOT
}

variable "tenant_primary_domain" {
  type        = string
  description = <<EOT
Primary domain of the Entra tenant (e.g. ``wiley-tech.onmicrosoft.com``).
Used by helper scripts and embedded in seeded EntraTenantLink rows.
EOT
}

variable "display_name_prefix" {
  type        = string
  default     = "AQP"
  description = "Prefix for every Entra resource display name. Pin to ``AQP-Dev`` in dev environments."
}

# -----------------------------------------------------------------------------
# App registration: aqp-staff (the staff login app)
# -----------------------------------------------------------------------------
variable "staff_app" {
  type = object({
    name                  = optional(string, "aqp-staff")
    description           = optional(string, "AQP staff login app for manage.aqp.fund.")
    redirect_uris         = optional(list(string), [])
    logout_urls           = optional(list(string), [])
    web_origins           = optional(list(string), [])
    public_client_enabled = optional(bool, false)
    sign_in_audience      = optional(string, "AzureADMyOrg") # single-tenant by default
  })
  default     = {}
  description = "Configuration for the staff login app registration."
}

# -----------------------------------------------------------------------------
# App registration: aqp-manage-api (the Resource Server)
# -----------------------------------------------------------------------------
variable "manage_api_app" {
  type = object({
    name             = optional(string, "aqp-manage-api")
    description      = optional(string, "AQP manage.aqp.fund Resource Server.")
    identifier_uri   = optional(string, "api://aqp-manage-api")
    sign_in_audience = optional(string, "AzureADMyOrg")
  })
  default     = {}
  description = "Configuration for the manage API Resource Server app registration."
}

variable "app_role_definitions" {
  type = list(object({
    id                   = string # stable v4 UUID — NEVER regenerate
    value                = string # the string that lands in the ``roles`` claim
    display_name         = string
    description          = string
    allowed_member_types = optional(list(string), ["User"])
  }))

  description = <<EOT
App roles defined on the manage API. Each ``id`` MUST stay stable
across plans — regenerating breaks every existing assignment. The
canonical seven for the AQP internal tenant ship as the default.
Extend by appending; NEVER reorder or remove without a migration plan.
EOT

  default = [
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a01"
      value        = "Admin"
      display_name = "AQP Admin"
      description  = "Full read/write on /manage/* + step-up MFA gate."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a02"
      value        = "Operator"
      display_name = "AQP Operator"
      description  = "Operational subset: workloads start/stop/scale, terraform plan."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a03"
      value        = "Auditor"
      display_name = "AQP Auditor"
      description  = "Read-only access to ledgers + evidence bundles."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a04"
      value        = "Compliance"
      display_name = "AQP Compliance"
      description  = "Read-only access to audit lake + evidence bundle export."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a05"
      value        = "Finance"
      display_name = "AQP Finance"
      description  = "FinOps + cost-attribution dashboards."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a06"
      value        = "Engineer"
      display_name = "AQP Engineer"
      description  = "Cell + workload + telemetry reads. No mutations."
    },
    {
      id           = "1eebf9b8-5f48-4f24-8c62-7ad5f03b7a07"
      value        = "Viewer"
      display_name = "AQP Viewer"
      description  = "Top-level read-only. Default for new staff before role assignment."
    },
  ]
}

# -----------------------------------------------------------------------------
# Directory groups
# -----------------------------------------------------------------------------
variable "groups" {
  type = list(object({
    key                = string # local key, used for outputs + role bindings
    display_name       = string
    description        = string
    role_values        = list(string) # references ``app_role_definitions[*].value``
    security_only      = optional(bool, true)
    assignable_to_role = optional(bool, false) # set true for roles using PIM
  }))

  description = <<EOT
Directory groups managed by Terraform. ``role_values`` MUST reference
existing entries in ``app_role_definitions``; the module asserts
this invariant in main.tf. Group membership is NOT managed here —
HR and Security own membership via the Azure Portal / Entitlement
Management.
EOT

  default = [
    {
      key          = "admins"
      display_name = "AQP-Admins"
      description  = "AQP super-admin staff. Step-up MFA + named-location gated. Membership requires CTO sign-off."
      role_values  = ["Admin"]
    },
    {
      key          = "operations"
      display_name = "AQP-Operations"
      description  = "AQP on-call SRE / DevOps staff."
      role_values  = ["Operator"]
    },
    {
      key          = "auditors"
      display_name = "AQP-Auditors"
      description  = "Internal + external auditors. Read-only ledger + evidence-bundle access."
      role_values  = ["Auditor"]
    },
    {
      key          = "compliance"
      display_name = "AQP-Compliance"
      description  = "AQP Compliance team. Audit lake + evidence bundle download."
      role_values  = ["Compliance", "Auditor"]
    },
    {
      key          = "finance"
      display_name = "AQP-Finance"
      description  = "AQP Finance + FinOps."
      role_values  = ["Finance"]
    },
    {
      key          = "engineering"
      display_name = "AQP-Engineering"
      description  = "AQP product + platform engineering."
      role_values  = ["Engineer"]
    },
    {
      key          = "soc"
      display_name = "AQP-SOC"
      description  = "Security Operations Center. Operator + Auditor combined."
      role_values  = ["Operator", "Auditor"]
    },
  ]
}

# -----------------------------------------------------------------------------
# CI federation: aqp-ci-github
# -----------------------------------------------------------------------------
variable "ci_app" {
  type = object({
    name             = optional(string, "aqp-ci-github")
    description      = optional(string, "Federated-credential-only app for GitHub Actions OIDC.")
    sign_in_audience = optional(string, "AzureADMyOrg")
  })
  default     = {}
  description = "Configuration for the CI federation app registration."
}

variable "ci_federated_credentials" {
  type = list(object({
    name        = string
    description = string
    # The full subject value the GitHub OIDC token presents. Format:
    #   repo:<owner>/<repo>:environment:<env>
    #   repo:<owner>/<repo>:ref:refs/heads/<branch>
    #   repo:<owner>/<repo>:pull_request
    # Per-environment / per-branch is REQUIRED — never use a
    # repo-wide wildcard.
    subject  = string
    audience = optional(string, "api://AzureADTokenExchange")
    issuer   = optional(string, "https://token.actions.githubusercontent.com")
  }))

  description = <<EOT
Per-environment / per-workflow federated credentials for GitHub
Actions OIDC. The subject claim MUST be a fully qualified scope —
NEVER ``repo:<owner>/<repo>:*``. The plan rejects subjects with ``*``
or ``ref:refs/heads/*``.
EOT

  default = [
    {
      name        = "github-main-push"
      description = "GitHub Actions push to main."
      subject     = "repo:julianwileymac/agentic_quant_platform:ref:refs/heads/main"
    },
    {
      name        = "github-prod-environment"
      description = "GitHub Actions deploy to prod environment."
      subject     = "repo:julianwileymac/agentic_quant_platform:environment:prod"
    },
    {
      name        = "github-pull-request"
      description = "GitHub Actions PR plan-only validations."
      subject     = "repo:julianwileymac/agentic_quant_platform:pull_request"
    },
  ]
}

# -----------------------------------------------------------------------------
# Named locations + CA policy data sources
# -----------------------------------------------------------------------------
variable "named_locations" {
  type = list(object({
    display_name = string
    ip_ranges    = list(string)
    is_trusted   = optional(bool, true)
  }))
  description = <<EOT
Named locations representing AQP-trusted IP ranges. Conditional Access
policies that gate the Admin role MUST reference at least one named
location from this list. Inputs are normalised to CIDR; the plan
rejects non-CIDR strings.
EOT
  default = [
    {
      display_name = "AQP-Corp-VPN"
      ip_ranges    = ["10.10.0.0/16"]
    },
  ]
}

variable "ca_policy_references" {
  type = list(object({
    display_name = string
    purpose      = string # documentation only — what the policy enforces
  }))
  description = <<EOT
Conditional Access policies the module reads via data source so the
operator can confirm the policies exist before exposing the staff
app. CA policy CREATION is NOT in this module — Security authors
policies through the portal under P2 review.
EOT
  default = [
    {
      display_name = "AQP-Admins-MFA-Required"
      purpose      = "Step-up MFA + FIDO2 on every Admin role token request."
    },
    {
      display_name = "AQP-Block-Risky-Sign-Ins"
      purpose      = "Blocks sign-ins flagged Medium+ by Identity Protection."
    },
  ]
}
