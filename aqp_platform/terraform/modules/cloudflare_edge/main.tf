/**
 * Cloudflare Zero Trust edge module — tunnel + DNS + Access app.
 *
 * Provisions:
 *
 * - A remotely-managed `cloudflare_zero_trust_tunnel_cloudflared`
 *   (the AQP CloudflareProvider mints the tunnel secret + tunnel
 *   token via the API after `terraform apply`).
 * - DNS records pointing the configured public hostnames at the
 *   tunnel's CNAME target (one record per hostname).
 * - A Cloudflare Access application protecting each hostname when
 *   `enable_access_app=true`; the matching include/require policies
 *   come from `var.access_policies`.
 *
 * Lives next to `terraform/modules/auth0_identity` so identity +
 * edge stay co-managed. The `aqp_management_engine` plan wires this
 * into `terraform/environments/rpi/main.tf` so the previously hand-
 * operated `cloudflared` Deployment under
 * `rpi_kubernetes/kubernetes/base-services/cloudflared/` becomes
 * IaC-managed.
 */

variable "tunnel_name" {
  type        = string
  description = "Name shown in the Cloudflare dashboard."
}

variable "account_id" {
  type        = string
  description = "Cloudflare account id."
  sensitive   = true
}

variable "zone_id" {
  type        = string
  description = "Cloudflare DNS zone id."
}

variable "ingress_rules" {
  description = <<-EOT
    List of ingress rules. Each item is { hostname, service } —
    `hostname` is the public DNS name, `service` is the in-cluster
    upstream (e.g. `http://ingress-nginx-controller.ingress.svc.cluster.local:80`).
    A catch-all `http_status:404` is appended automatically.
  EOT
  type = list(object({
    hostname = string
    service  = string
  }))
  default = []
}

variable "enable_access_app" {
  type    = bool
  default = false
}

variable "access_app_name" {
  type    = string
  default = ""
}

variable "access_app_session_duration" {
  type    = string
  default = "24h"
}

variable "access_policies" {
  description = <<-EOT
    List of Access policies. Each item: { name, decision, includes
    (list of { email_domain | group | everyone }), requires (optional
    list of the same), excludes (optional list of the same) }.
  EOT
  type        = any
  default     = []
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "tunnel" {
  account_id = var.account_id
  name       = var.tunnel_name
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "config" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.tunnel.id

  config = {
    ingress = concat(
      [
        for rule in var.ingress_rules : {
          hostname = rule.hostname
          service  = rule.service
        }
      ],
      [
        {
          service = "http_status:404"
        }
      ],
    )
  }
}

# One CNAME per hostname pointing at the tunnel's edge target.
resource "cloudflare_dns_record" "tunnel_routes" {
  for_each = {
    for idx, rule in var.ingress_rules : rule.hostname => rule
  }

  zone_id = var.zone_id
  name    = each.value.hostname
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.tunnel.id}.cfargotunnel.com"
  ttl     = 1
  proxied = true
  comment = "AQP Management Engine tunnel route for ${each.value.hostname}"
}

# Optional Access app guarding every hostname.
resource "cloudflare_zero_trust_access_application" "app" {
  count = var.enable_access_app ? 1 : 0

  account_id                 = var.account_id
  name                       = coalesce(var.access_app_name, var.tunnel_name)
  domain                     = var.ingress_rules[0].hostname
  type                       = "self_hosted"
  session_duration           = var.access_app_session_duration
  auto_redirect_to_identity  = true
  app_launcher_visible       = true
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"
}

resource "cloudflare_zero_trust_access_policy" "policies" {
  for_each = var.enable_access_app ? {
    for p in var.access_policies : p.name => p
  } : {}

  account_id     = var.account_id
  application_id = cloudflare_zero_trust_access_application.app[0].id
  name           = each.value.name
  decision       = each.value.decision
  include        = lookup(each.value, "includes", [])
  require        = lookup(each.value, "requires", null)
  exclude        = lookup(each.value, "excludes", null)
}

output "tunnel_id" {
  value       = cloudflare_zero_trust_tunnel_cloudflared.tunnel.id
  description = "Cloudflare tunnel id (use for `cloudflared --token`)."
}

output "tunnel_cname_target" {
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.tunnel.id}.cfargotunnel.com"
  description = "CNAME target the in-cluster cloudflared sidecar should advertise."
}

output "access_app_id" {
  value       = try(cloudflare_zero_trust_access_application.app[0].id, null)
  description = "Cloudflare Access app id (null when enable_access_app=false)."
}

output "access_app_aud" {
  value       = try(cloudflare_zero_trust_access_application.app[0].aud, null)
  description = "Access app AUD tag — set as AQP_CF_ACCESS_AUD."
  sensitive   = true
}
