###############################################################################
# environments/minimum — application tier on top of infrastructure/envs/minimum.
#
# Partial S3 backend: render backend.hcl from infrastructure/envs/minimum
# before ``terraform init`` (or just rely on init -backend-config args).
###############################################################################
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws",    version = "~> 6.21" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
  backend "s3" {}
}
