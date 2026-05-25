terraform {
  required_providers {
    auth0 = {
      source  = "auth0/auth0"
      version = ">= 1.0.0, < 2.0.0"
    }
  }
}

# Auth0 Action — outbound SCIM provisioning to AWS IAM Identity Center
# + Microsoft Graph (Entra). Skeleton: ships in inactive form. The
# real payload bodies land in a follow-up PR; this module exists so
# the secret-resolution wiring + Action shell are testable today.
resource "auth0_action" "scim_outbound" {
  name        = "aqp-scim-outbound"
  runtime     = "node18"
  deploy      = true
  code        = file("${path.module}/../../../../../auth0/actions/scim-outbound.js")

  supported_triggers {
    id      = "post-user-registration"
    version = "v2"
  }

  dynamic "secrets" {
    for_each = var.secrets
    content {
      name  = secrets.key
      value = secrets.value
    }
  }
}

# Bind the Action into the post-user-registration trigger chain.
# The bind is gated behind `var.enable_action_binding` so the
# skeleton ships disabled while the payload work is pending.
resource "auth0_trigger_actions" "scim_outbound_trigger" {
  count   = var.enable_action_binding ? 1 : 0
  trigger = "post-user-registration"

  actions {
    id           = auth0_action.scim_outbound.id
    display_name = auth0_action.scim_outbound.name
  }
}
