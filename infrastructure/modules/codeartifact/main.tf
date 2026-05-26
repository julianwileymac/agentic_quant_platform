###############################################################################
# modules/codeartifact — internal Python wheel + npm registry.
#
# Used by the AWS-native pipeline option so prod builds don't pull
# directly from public PyPI / npm.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "domain_name" {
  type    = string
  default = "aqp"
}
variable "kms_key_arn" { type = string }
variable "repositories" {
  type    = list(string)
  default = ["aqp-pypi", "aqp-npm"]
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_codeartifact_domain" "this" {
  domain         = var.domain_name
  encryption_key = var.kms_key_arn
  tags           = var.tags
}

resource "aws_codeartifact_repository" "pypi_upstream" {
  count        = contains(var.repositories, "aqp-pypi") ? 1 : 0
  domain       = aws_codeartifact_domain.this.domain
  repository   = "pypi-store"
  description  = "Cached pass-through to public PyPI."

  external_connections {
    external_connection_name = "public:pypi"
  }

  tags = var.tags
}

resource "aws_codeartifact_repository" "pypi_internal" {
  count       = contains(var.repositories, "aqp-pypi") ? 1 : 0
  domain      = aws_codeartifact_domain.this.domain
  repository  = "aqp-pypi"
  description = "Internal AQP wheels."
  upstream {
    repository_name = aws_codeartifact_repository.pypi_upstream[0].repository
  }
  tags = var.tags
}

resource "aws_codeartifact_repository" "npm_upstream" {
  count       = contains(var.repositories, "aqp-npm") ? 1 : 0
  domain      = aws_codeartifact_domain.this.domain
  repository  = "npm-store"
  description = "Cached pass-through to public npm."

  external_connections {
    external_connection_name = "public:npmjs"
  }
  tags = var.tags
}

resource "aws_codeartifact_repository" "npm_internal" {
  count       = contains(var.repositories, "aqp-npm") ? 1 : 0
  domain      = aws_codeartifact_domain.this.domain
  repository  = "aqp-npm"
  description = "Internal AQP node packages."
  upstream {
    repository_name = aws_codeartifact_repository.npm_upstream[0].repository
  }
  tags = var.tags
}
