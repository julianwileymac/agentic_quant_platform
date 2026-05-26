###############################################################################
# modules/account — Service-Catalog-backed account factory wrapper.
#
# Creates a workload account inside an OU and seeds the
# `AqpTerraformExecutionRole` (cross-account assume target).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" {
  description = "Account display name (e.g. 'aqp-dev')."
  type        = string
}

variable "email" {
  description = "Root email for the new account."
  type        = string
}

variable "parent_id" {
  description = "OU id to create the account in."
  type        = string
}

variable "external_id" {
  description = "External id for the assume-role trust policy."
  type        = string
  sensitive   = true
}

variable "shared_services_account_id" {
  description = "Account id of shared-services that gets assume-role rights."
  type        = string
}

resource "aws_organizations_account" "this" {
  name              = var.name
  email             = var.email
  parent_id         = var.parent_id
  iam_user_access_to_billing = "DENY"
  close_on_deletion = false

  lifecycle {
    ignore_changes = [role_name]
  }
}

###############################################################################
# Bootstrap-time provider that assumes into the new account once it exists.
###############################################################################

provider "aws" {
  alias = "child"
  assume_role {
    role_arn = "arn:aws:iam::${aws_organizations_account.this.id}:role/OrganizationAccountAccessRole"
  }
  region = "us-east-1"
}

resource "aws_iam_role" "terraform_execution" {
  provider           = aws.child
  name               = "AqpTerraformExecutionRole"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { AWS = "arn:aws:iam::${var.shared_services_account_id}:root" }
      Action   = "sts:AssumeRole"
      Condition = {
        StringEquals = { "sts:ExternalId" = var.external_id }
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "terraform_execution_admin" {
  provider   = aws.child
  role       = aws_iam_role.terraform_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

###############################################################################
# Permission boundary that the AqpTerraformExecutionRole MUST attach to
# every IAM principal it creates — prevents privilege escalation out of
# the platform-team scope.
###############################################################################

resource "aws_iam_policy" "terraform_permissions_boundary" {
  provider = aws.child
  name     = "AqpTerraformPermissionsBoundary"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AllowEverythingExceptOrgAdmin"
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      },
      {
        Sid    = "DenyOrgAndAccountActions"
        Effect = "Deny"
        Action = [
          "organizations:*",
          "account:*",
          "iam:DeleteRolePermissionsBoundary",
          "iam:DeleteUserPermissionsBoundary",
        ]
        Resource = "*"
      }
    ]
  })
}
