###############################################################################
# modules/codebuild — per-service build project for the AWS-native pipeline.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "buildspec_path" { type = string }
variable "service_role_arn" { type = string }
variable "compute_type" {
  type    = string
  default = "BUILD_GENERAL1_LARGE"
}
variable "image" {
  type    = string
  default = "aws/codebuild/standard:7.0"
}
variable "kms_key_arn" { type = string }
variable "environment_variables" {
  type    = map(string)
  default = {}
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_codebuild_project" "this" {
  name          = var.name
  service_role  = var.service_role_arn
  build_timeout = 60

  artifacts { type = "CODEPIPELINE" }

  environment {
    compute_type    = var.compute_type
    image           = var.image
    type            = "LINUX_CONTAINER"
    privileged_mode = true # needed for buildx + Cosign keyless

    dynamic "environment_variable" {
      for_each = var.environment_variables
      content {
        name  = environment_variable.key
        value = environment_variable.value
      }
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = var.buildspec_path
  }

  encryption_key = var.kms_key_arn
  tags           = var.tags
}
