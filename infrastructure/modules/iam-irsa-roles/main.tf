###############################################################################
# modules/iam-irsa-roles — generic IRSA role for a (namespace, sa) pair.
#
# Reusable building block; per-cluster compositions instantiate one
# instance per service account that needs AWS API access. The
# `policies` map attaches arbitrary policy ARNs.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "oidc_provider_url" { type = string }
variable "namespace" { type = string }
variable "service_account" { type = string }
variable "policy_arns" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.service_account}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${replace(var.oidc_provider_url, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = var.name
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "this" {
  for_each   = toset(var.policy_arns)
  role       = aws_iam_role.this.name
  policy_arn = each.value
}
