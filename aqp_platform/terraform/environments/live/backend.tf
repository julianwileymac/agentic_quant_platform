###############################################################################
# Live environment Terraform state backend — partial S3 config.
#
# Phase G of the AWS hybrid rollout. The earlier hardcoded bucket + DynamoDB
# table only worked for the single ``wiley-tech`` account; the partial
# config below lets the same ``environments/live/`` tree target whichever
# account the operator bootstrapped (dev / staging / prod) by passing the
# matching ``backend.hcl`` at init time::
#
#     cd aqp_platform/terraform/environments/live
#     terraform init -reconfigure -backend-config=backend.hcl
#
# The backend.hcl contents come from the
# ``infrastructure/bootstrap/`` outputs (the per-account state bucket +
# DynamoDB lock table + KMS CMK that bootstrap/main.tf provisions).
#
# See ``backend.hcl.example`` for the expected field set.
###############################################################################
terraform {
  backend "s3" {}
}
