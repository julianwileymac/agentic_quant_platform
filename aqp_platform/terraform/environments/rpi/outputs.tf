output "namespace" {
  value = module.target.namespace
}

output "api_url" {
  value = var.rpi_ingress_host != "" ? "https://${var.rpi_ingress_host}/api" : ""
}

output "frontend_url" {
  value = var.rpi_ingress_host != "" ? "https://${var.rpi_ingress_host}/" : ""
}

output "auth0_domain" {
  value = var.auth0_domain
}

output "images" {
  value = local.images
}

output "cloudflare_tunnel_id" {
  value       = try(module.cloudflare_edge[0].tunnel_id, null)
  description = "Cloudflare tunnel id when cloudflare_enabled=true, else null."
}

output "cloudflare_tunnel_cname_target" {
  value       = try(module.cloudflare_edge[0].tunnel_cname_target, null)
  description = "CNAME target the cloudflared sidecar should advertise."
}

output "cloudflare_access_app_id" {
  value       = try(module.cloudflare_edge[0].access_app_id, null)
  description = "Cloudflare Access app id (null when access app disabled)."
}
