###############################################################################
# modules/route53-zones — public + private Route 53 hosted zones.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "public_zone_name" { type = string }
variable "private_zone_name" { type = string }
variable "vpc_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_route53_zone" "public" {
  name = var.public_zone_name
  tags = merge(var.tags, { kind = "public" })
}

resource "aws_route53_zone" "private" {
  name = var.private_zone_name
  vpc { vpc_id = var.vpc_id }
  tags = merge(var.tags, { kind = "private" })
}
