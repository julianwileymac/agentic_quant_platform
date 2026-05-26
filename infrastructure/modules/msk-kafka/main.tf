###############################################################################
# modules/msk-kafka — Managed Streaming for Apache Kafka.
#
# IAM-authn enabled so service principals (paper-trading workers,
# market-data ingesters) can connect via SigV4 instead of broker-side
# username/password. Encryption-in-transit + at-rest with the
# platform's customer-managed KMS key.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "kms_key_arn" { type = string }
variable "kafka_version" {
  type    = string
  default = "3.7.x"
}
variable "broker_count" {
  type    = number
  default = 3
}
variable "broker_instance_type" {
  type    = string
  default = "kafka.m7g.large"
}
variable "tags" {
  type    = map(string)
  default = {}
}

resource "aws_security_group" "msk" {
  name        = "${var.name}-msk"
  description = "Allow Kafka from inside the VPC."
  vpc_id      = var.vpc_id
  ingress {
    from_port = 9092
    to_port   = 9098
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

resource "aws_msk_cluster" "this" {
  cluster_name           = var.name
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type   = var.broker_instance_type
    client_subnets  = var.subnet_ids
    security_groups = [aws_security_group.msk.id]
    storage_info {
      ebs_storage_info {
        volume_size = 200
      }
    }
  }

  encryption_info {
    encryption_at_rest_kms_key_arn = var.kms_key_arn
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  client_authentication {
    sasl {
      iam = true
    }
  }

  open_monitoring {
    prometheus {
      jmx_exporter { enabled_in_broker = true }
      node_exporter { enabled_in_broker = true }
    }
  }

  logging_info {
    broker_logs {
      cloudwatch_logs { enabled = true; log_group = aws_cloudwatch_log_group.msk.name }
    }
  }

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/aws/msk/${var.name}"
  retention_in_days = 30
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}
