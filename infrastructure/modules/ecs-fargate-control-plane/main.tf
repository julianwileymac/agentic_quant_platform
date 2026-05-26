###############################################################################
# modules/ecs-fargate-control-plane — Fargate cluster + per-service Fargate task.
#
# Hosts the AWS-native admin BFF (``aqp-admin``) + the AgentCore reverse
# proxy (``aqp-agentcore-proxy``). The EKS Karpenter foundation continues
# to host the quant runtime workloads (workers, Iceberg writers, MLflow,
# Strimzi, Flink) per the operator's hybrid topology decision; this module
# only provisions the Fargate slice.
#
# Each task ships with an ADOT sidecar (image pinned by the operator).
# Per AGENTS rule 4 the application emits OTLP traces / metrics to
# ``localhost:4317``; the sidecar fans them out to X-Ray + CloudWatch
# Application Signals. Per AGENTS rule 26 secrets ARE NEVER inlined —
# every secret is a ``secrets[]`` reference to a Secrets Manager ARN.
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enhanced"
  }

  configuration {
    execute_command_configuration {
      logging = "OVERRIDE"
      log_configuration {
        cloud_watch_log_group_name = aws_cloudwatch_log_group.ecs_exec.name
      }
    }
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-cluster-${var.environment}" })
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name = aws_ecs_cluster.this.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = var.environment == "prod" ? 100 : 80
    base              = 1
  }

  dynamic "default_capacity_provider_strategy" {
    for_each = var.environment != "prod" ? [1] : []
    content {
      capacity_provider = "FARGATE_SPOT"
      weight            = 20
    }
  }
}

resource "aws_cloudwatch_log_group" "ecs_exec" {
  name              = "/aws/ecs/${var.name_prefix}-cluster-${var.environment}/exec"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_security_group" "tasks" {
  name        = "${var.name_prefix}-fargate-tasks-${var.environment}"
  description = "ECS Fargate tasks — accept traffic from the ALB SG only."
  vpc_id      = var.vpc_id

  ingress {
    description     = "Application ports from the ALB SG."
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }

  egress {
    description = "Egress to AWS API endpoints + internet."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

###############################################################################
# Task execution role (pull from ECR + write CloudWatch Logs + read secrets).
###############################################################################

data "aws_iam_policy_document" "execution_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-fargate-exec-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.execution_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_extra" {
  statement {
    sid       = "ReadSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns_for_tasks
  }
  statement {
    sid       = "ReadSSM"
    effect    = "Allow"
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:*:*:parameter/aqp/${var.environment}/*"]
  }
  statement {
    sid       = "KMSDecrypt"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = var.kms_key_arn != null ? [var.kms_key_arn] : ["*"]
  }
}

resource "aws_iam_role_policy" "execution_extra" {
  name   = "${var.name_prefix}-fargate-exec-extras-${var.environment}"
  role   = aws_iam_role.execution.name
  policy = data.aws_iam_policy_document.execution_extra.json
}

###############################################################################
# Per-service task role (application IAM — passthrough to caller).
###############################################################################

resource "aws_iam_role" "task" {
  for_each = var.services

  name               = "${var.name_prefix}-task-${each.key}-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.execution_trust.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "task_managed" {
  for_each = {
    for pair in flatten([
      for sk, sv in var.services : [
        for arn in sv.task_role_policy_arns : { svc = sk, arn = arn }
      ]
    ]) : "${pair.svc}-${pair.arn}" => pair
  }

  role       = aws_iam_role.task[each.value.svc].name
  policy_arn = each.value.arn
}

###############################################################################
# Per-service log group, task definition, service.
###############################################################################

resource "aws_cloudwatch_log_group" "service" {
  for_each = var.services

  name              = "/aws/ecs/${var.name_prefix}-${each.key}-${var.environment}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.kms_key_arn
  tags              = var.tags
}

resource "aws_ecs_task_definition" "this" {
  for_each = var.services

  family                   = "${var.name_prefix}-${each.key}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task[each.key].arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = each.value.cpu_architecture
  }

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = each.value.image
      essential = true
      portMappings = [
        for p in each.value.ports : {
          containerPort = p
          protocol      = "tcp"
        }
      ]
      environment = [
        { name = "AQP_ENVIRONMENT", value = var.environment },
        { name = "AQP_OTEL_ENDPOINT", value = "http://localhost:4317" },
      ]
      secrets = each.value.secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.service[each.key].name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = each.key
        }
      }
    },
    {
      name      = "adot-collector"
      image     = var.adot_collector_image
      essential = false
      environment = [
        { name = "AOT_CONFIG_CONTENT", value = var.adot_config_yaml },
      ]
      portMappings = [
        { containerPort = 4317, protocol = "tcp" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.service[each.key].name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "adot"
        }
      }
    },
  ])

  tags = var.tags
}

data "aws_region" "current" {}

resource "aws_ecs_service" "this" {
  for_each = var.services

  name                 = "${var.name_prefix}-${each.key}-${var.environment}"
  cluster              = aws_ecs_cluster.this.id
  task_definition      = aws_ecs_task_definition.this[each.key].arn
  desired_count        = each.value.desired_count
  launch_type          = "FARGATE"
  force_new_deployment = false
  enable_execute_command = true
  propagate_tags       = "SERVICE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.value.alb_target_group_arn != null ? [1] : []
    content {
      target_group_arn = each.value.alb_target_group_arn
      container_name   = each.key
      container_port   = each.value.ports[0]
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.tags
}

resource "aws_ssm_parameter" "cluster_name" {
  name  = "/aqp/${var.environment}/ecs_cluster_name"
  type  = "String"
  value = aws_ecs_cluster.this.name
  tags  = var.tags
}

resource "aws_ssm_parameter" "cluster_arn" {
  name  = "/aqp/${var.environment}/ecs_cluster_arn"
  type  = "String"
  value = aws_ecs_cluster.this.arn
  tags  = var.tags
}

resource "aws_ssm_parameter" "service_names" {
  name  = "/aqp/${var.environment}/ecs_service_names"
  type  = "StringList"
  value = join(",", [for k, _ in var.services : aws_ecs_service.this[k].name])
  tags  = var.tags
}
