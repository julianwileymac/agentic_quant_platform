variable "secrets" {
  description = <<-EOT
    Auth0 Action Secrets injected into scim-outbound.
    The map keys MUST match the names declared in
    auth0/actions/scim-outbound.config.json.

    Resolve concrete values through CredentialResolver in the calling
    stack — never hard-code secrets here. The platform's Vault
    namespace owns SCIM_AWS_BEARER + GRAPH_CLIENT_SECRET rotation.
  EOT
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "enable_action_binding" {
  description = <<-EOT
    Bind the SCIM-outbound Action into the post-user-registration
    trigger chain when true. Defaults to false so the skeleton
    Action ships in deployed-but-inactive form.
  EOT
  type        = bool
  default     = false
}
