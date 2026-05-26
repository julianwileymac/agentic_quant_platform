###############################################################################
# modules/codepipeline — AWS-native CI orchestrator (alternative to GHA).
#
# Wraps a CodePipeline that pulls from CodeStar Connections (GitHub),
# runs CodeBuild stages per service, and pushes images to the per-account
# ECR. Used only when the operator picks the "sovereign cloud" path —
# GitHub Actions remains the default CI per Phase 3.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "github_connection_arn" { type = string }
variable "source_repo" { type = string }
variable "source_branch" {
  type    = string
  default = "main"
}
variable "build_project_name" { type = string }
variable "artifact_bucket" { type = string }
variable "kms_key_arn" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_iam_role" "pipeline" {
  name = "${var.name}-pipeline"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "pipeline" {
  role = aws_iam_role.pipeline.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "codestar-connections:UseConnection",
          "codebuild:BatchGetBuilds",
          "codebuild:StartBuild",
          "s3:*",
          "kms:Decrypt",
          "kms:GenerateDataKey",
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_codepipeline" "this" {
  name     = var.name
  role_arn = aws_iam_role.pipeline.arn

  artifact_store {
    location = var.artifact_bucket
    type     = "S3"
    encryption_key {
      id   = var.kms_key_arn
      type = "KMS"
    }
  }

  stage {
    name = "Source"
    action {
      name             = "GitHub"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["src"]
      configuration = {
        ConnectionArn    = var.github_connection_arn
        FullRepositoryId = var.source_repo
        BranchName       = var.source_branch
      }
    }
  }
  stage {
    name = "Build"
    action {
      name             = "Build"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["src"]
      output_artifacts = ["build"]
      configuration = {
        ProjectName = var.build_project_name
      }
    }
  }
  tags = var.tags
}
