###############################################################################
# modules/acm-pca — Private CA for internal mTLS (cert-manager AWSPCAIssuer).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "common_name" { type = string }
variable "country" {
  type    = string
  default = "US"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_acmpca_certificate_authority" "this" {
  type = "ROOT"
  certificate_authority_configuration {
    key_algorithm     = "RSA_4096"
    signing_algorithm = "SHA512WITHRSA"
    subject {
      common_name = var.common_name
      country     = var.country
    }
  }
  permanent_deletion_time_in_days = 7
  tags                            = merge(var.tags, { Name = var.name })
}

# A self-signed root certificate so the CA can immediately issue.
resource "aws_acmpca_certificate" "root" {
  certificate_authority_arn   = aws_acmpca_certificate_authority.this.arn
  certificate_signing_request = aws_acmpca_certificate_authority.this.certificate_signing_request
  signing_algorithm           = "SHA512WITHRSA"
  template_arn                = "arn:aws:acm-pca:::template/RootCACertificate/V1"
  validity {
    type  = "YEARS"
    value = 10
  }
}

resource "aws_acmpca_certificate_authority_certificate" "root" {
  certificate_authority_arn = aws_acmpca_certificate_authority.this.arn
  certificate               = aws_acmpca_certificate.root.certificate
  certificate_chain         = aws_acmpca_certificate.root.certificate_chain
}
