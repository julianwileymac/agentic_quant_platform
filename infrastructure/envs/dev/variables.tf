variable "region" {
  type    = string
  default = "us-east-1"
}
variable "account_id" {
  type = string
}
variable "external_id" {
  type      = string
  sensitive = true
}
variable "kms_key_arn" {
  type = string
}
variable "github_oidc_provider_arn" {
  type = string
}
variable "argocd_domain" {
  type    = string
  default = "argo.dev.aqp.internal"
}
variable "argocd_oidc_issuer" {
  type    = string
  default = ""
}
variable "argocd_oidc_client_id" {
  type    = string
  default = ""
}
variable "grafana_admin_password" {
  type      = string
  sensitive = true
}
