###############################################################################
# modules/github-oidc — IAM role assumed by GitHub Actions via OIDC.
#
# One role per environment. The trust policy locks ``sub`` to a
# specific repo + ref pattern so a token minted on a topic branch
# cannot deploy to prod.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "oidc_provider_arn" { type = string }
variable "github_org" { type = string }
variable "github_repo" { type = string }
variable "ref_patterns" {
  description = "Allowed ref patterns (e.g. 'refs/heads/main', 'refs/tags/v*')."
  type        = list(string)
}
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
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        for ref in var.ref_patterns : "repo:${var.github_org}/${var.github_repo}:ref:${ref}"
      ]
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
