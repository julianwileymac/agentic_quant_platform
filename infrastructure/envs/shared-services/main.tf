###############################################################################
# envs/shared-services — single composition for the shared-services account.
#
# Hosts ECR (with cross-region replication), CodeArtifact, the ArgoCD
# hub cluster, and the audit-archive bucket. Workload accounts depend
# on outputs from this stack.
###############################################################################

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "account_id" {
  description = "AWS account id for shared-services."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN from bootstrap/."
  type        = string
}

module "ecr" {
  source             = "../../modules/ecr-repositories"
  kms_key_arn        = var.kms_key_arn
  account_id         = var.account_id
  region             = var.region
  enable_replication = true
}

module "codeartifact" {
  source      = "../../modules/codeartifact"
  kms_key_arn = var.kms_key_arn
  domain_name = "aqp"
}

module "audit_archive" {
  source                      = "../../modules/s3-data-lake"
  name                        = "aqp-audit-archive-${var.account_id}"
  kms_key_arn                 = var.kms_key_arn
  enable_object_lock          = true
  object_lock_retention_years = 7
  tags = {
    purpose = "audit-archive"
    finra   = "rule-4511"
    sec     = "rule-17a-4-f-2"
  }
}

output "ecr_repository_urls" { value = module.ecr.repository_urls }
output "codeartifact_domain" { value = module.codeartifact.domain_name }
output "audit_archive_bucket" { value = module.audit_archive.bucket }
