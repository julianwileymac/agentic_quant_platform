###############################################################################
# modules/rds-postgres — multi-AZ Postgres + KMS + IAM auth + PI.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws    = { source = "hashicorp/aws", version = "~> 5.70" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "kms_key_arn" { type = string }
variable "instance_class" {
  type    = string
  default = "db.m6i.large"
}
variable "allocated_storage" {
  type    = number
  default = 100
}
variable "multi_az" {
  type    = bool
  default = true
}
variable "engine_version" {
  type    = string
  default = "16.4"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "random_password" "master" {
  length           = 32
  special          = true
  override_special = "!@#$%^&*()-_=+"
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.name}-rds"
  description = "Allow Postgres from inside the VPC."
  vpc_id      = var.vpc_id

  ingress {
    from_port = 5432
    to_port   = 5432
    protocol  = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_db_instance" "this" {
  identifier              = var.name
  engine                  = "postgres"
  engine_version          = var.engine_version
  instance_class          = var.instance_class
  allocated_storage       = var.allocated_storage
  storage_encrypted       = true
  kms_key_id              = var.kms_key_arn
  storage_type            = "gp3"
  multi_az                = var.multi_az
  username                = "aqp_admin"
  password                = random_password.master.result
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [aws_security_group.this.id]
  publicly_accessible     = false
  iam_database_authentication_enabled = true
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = var.kms_key_arn
  performance_insights_retention_period = 7
  monitoring_interval     = 60
  copy_tags_to_snapshot   = true
  deletion_protection     = true
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Sun:04:00-Sun:05:00"
  apply_immediately       = false
  enabled_cloudwatch_logs_exports = ["postgresql"]
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${var.name}-final"
  tags = merge(var.tags, { Name = var.name })

  lifecycle {
    ignore_changes = [password]
  }
}
