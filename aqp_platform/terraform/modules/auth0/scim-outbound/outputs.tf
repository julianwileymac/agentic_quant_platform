output "action_id" {
  description = "Auth0 Action id (use to bind into additional triggers downstream)."
  value       = auth0_action.scim_outbound.id
}

output "action_name" {
  description = "Auth0 Action display name."
  value       = auth0_action.scim_outbound.name
}

output "binding_active" {
  description = "Whether the post-user-registration trigger binding is active."
  value       = var.enable_action_binding
}
