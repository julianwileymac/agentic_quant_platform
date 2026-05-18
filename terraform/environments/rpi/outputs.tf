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
