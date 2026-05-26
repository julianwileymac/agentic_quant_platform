###############################################################################
# modules/vpc — /16 VPC with private + public + intra subnets + VPC endpoints.
#
# Composes the official `terraform-aws-modules/vpc/aws` module with the
# AQP defaults: 3 AZs, private + public + intra, NAT in public for
# egress, gateway endpoints for S3 + DynamoDB, interface endpoints
# for ECR + STS + Secrets Manager + SSM + KMS + CloudWatch Logs.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "cidr" {
  type    = string
  default = "10.0.0.0/16"
}
variable "azs_count" {
  type    = number
  default = 3
}
variable "tags" {
  type    = map(string)
  default = {}
}

# --- NAT topology -----------------------------------------------------------
# Defaults preserve the prod-shape (one NAT per AZ). The minimum env
# composition flips ``single_nat_gateway=true`` to collapse to a single
# ~$32/mo NAT shared across every AZ (the documented dev/preview pattern).
variable "single_nat_gateway" {
  type        = bool
  default     = false
  description = "When true, route every private subnet through one NAT (cheap)."
}

variable "enable_interface_endpoints" {
  type        = bool
  default     = true
  description = "Provision the per-AWS-API interface endpoints (chargeable)."
}

data "aws_availability_zones" "available" { state = "available" }

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.azs_count)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = var.name
  cidr = var.cidr

  azs              = local.azs
  private_subnets  = [for i in range(var.azs_count) : cidrsubnet(var.cidr, 4, i)]
  public_subnets   = [for i in range(var.azs_count) : cidrsubnet(var.cidr, 4, i + var.azs_count)]
  intra_subnets    = [for i in range(var.azs_count) : cidrsubnet(var.cidr, 4, i + var.azs_count * 2)]

  enable_nat_gateway     = true
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = !var.single_nat_gateway

  enable_dns_hostnames = true
  enable_dns_support   = true

  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
  flow_log_max_aggregation_interval    = 60

  public_subnet_tags = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
    "karpenter.sh/discovery"          = var.name
  }

  tags = merge(var.tags, { Name = var.name })
}

###############################################################################
# Gateway endpoints (free) — keep S3 + DynamoDB traffic on the AWS backbone.
###############################################################################

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
  tags              = merge(var.tags, { Name = "${var.name}-s3" })
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${data.aws_region.current.name}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
  tags              = merge(var.tags, { Name = "${var.name}-ddb" })
}

###############################################################################
# Interface endpoints — chargeable but cut NAT egress for AWS APIs.
###############################################################################

locals {
  interface_endpoints = toset([
    "ecr.api",
    "ecr.dkr",
    "sts",
    "secretsmanager",
    "ssm",
    "ssmmessages",
    "ec2",
    "ec2messages",
    "kms",
    "logs",
    "monitoring",
    "elasticloadbalancing",
    "autoscaling",
    "eks",
    "eks-auth",
  ])
}

resource "aws_security_group" "vpc_endpoints" {
  name        = "${var.name}-vpc-endpoints"
  description = "Allow HTTPS from inside the VPC to interface endpoints."
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_vpc_endpoint" "interfaces" {
  for_each            = var.enable_interface_endpoints ? local.interface_endpoints : toset([])
  vpc_id              = module.vpc.vpc_id
  service_name        = "com.amazonaws.${data.aws_region.current.name}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = module.vpc.private_subnets
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags                = merge(var.tags, { Name = "${var.name}-${each.value}" })
}

data "aws_region" "current" {}
