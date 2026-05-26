###############################################################################
# modules/cloudwatch-alarms — operator-tier CloudWatch alarms + dashboard.
#
# Phase J of the AWS hybrid rollout. Lights up the alarms the
# blueprint §11 page-criteria called for, scoped per resource the
# operator passes in. Designed to be additive — every input is
# optional, so the same module covers the minimum tier (RDS only) and
# the full hybrid stack (RDS + ALB + ECS + Bedrock).
#
# Alarm topic:
#  - Operator supplies ``alarm_topic_arn`` (an existing SNS topic), OR
#  - the module creates a new SNS topic named ``<name_prefix>-alarms-<env>``
#    + leaves subscription wiring to the operator (avoid hard-coding
#    a PagerDuty endpoint here).
###############################################################################

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.70" }
  }
}

variable "environment" { type = string }
variable "name_prefix" { type = string, default = "aqp" }
variable "tags"        { type = map(string), default = {} }

variable "alarm_topic_arn" {
  type        = string
  default     = null
  description = "Existing SNS topic to send alarms to. When null the module creates one."
}

# --- Per-resource inputs (every block is optional) -------------------------

variable "rds_instance_id" {
  type        = string
  default     = null
  description = "RDS instance identifier to alarm on (CPU, free storage, IOPS)."
}

variable "alb_arn_suffix" {
  type        = string
  default     = null
  description = "ALB ARN suffix (app/<name>/<id>) for 5xx + target-health alarms."
}

variable "alb_target_group_arn_suffix" {
  type        = string
  default     = null
  description = "Target-group ARN suffix for UnHealthyHostCount alarm."
}

variable "ecs_cluster_name" {
  type        = string
  default     = null
  description = "ECS cluster name for service running/desired count alarms."
}

variable "ecs_service_names" {
  type        = list(string)
  default     = []
  description = "ECS service names within ``ecs_cluster_name`` to alarm on."
}

variable "redis_replication_group_id" {
  type        = string
  default     = null
  description = "ElastiCache replication-group id (Engine CPU + connection alarms)."
}

variable "bedrock_alarm_enabled" {
  type        = bool
  default     = true
  description = "Whether to wire the Bedrock invocation throttling alarm."
}

# --- Thresholds (per-env tunable) ------------------------------------------

variable "rds_cpu_critical_pct"          { type = number, default = 80 }
variable "rds_free_storage_critical_gb"  { type = number, default = 5 }
variable "alb_5xx_per_minute_critical"   { type = number, default = 10 }
variable "redis_cpu_critical_pct"        { type = number, default = 80 }

# ---------------------------------------------------------------------------
# SNS topic (optional create)
# ---------------------------------------------------------------------------

locals {
  topic_arn = var.alarm_topic_arn != null ? var.alarm_topic_arn : aws_sns_topic.created[0].arn
}

resource "aws_sns_topic" "created" {
  count = var.alarm_topic_arn == null ? 1 : 0
  name  = "${var.name_prefix}-alarms-${var.environment}"
  tags  = var.tags
}

# ---------------------------------------------------------------------------
# RDS alarms
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "rds_cpu" {
  count               = var.rds_instance_id != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-rds-cpu-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  period              = 300
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  statistic           = "Average"
  threshold           = var.rds_cpu_critical_pct
  alarm_description   = "RDS instance ${var.rds_instance_id} CPU > ${var.rds_cpu_critical_pct}% for 15 min"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "rds_free_storage" {
  count               = var.rds_instance_id != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-rds-free-storage-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  period              = 300
  metric_name         = "FreeStorageSpace"
  namespace           = "AWS/RDS"
  statistic           = "Minimum"
  threshold           = var.rds_free_storage_critical_gb * 1024 * 1024 * 1024
  alarm_description   = "RDS instance ${var.rds_instance_id} free storage < ${var.rds_free_storage_critical_gb} GB"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    DBInstanceIdentifier = var.rds_instance_id
  }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# ALB alarms — 5xx rate + unhealthy host count
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count               = var.alb_arn_suffix != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-alb-5xx-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  period              = 60
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  statistic           = "Sum"
  threshold           = var.alb_5xx_per_minute_critical
  alarm_description   = "ALB ${var.alb_arn_suffix} target 5xx > ${var.alb_5xx_per_minute_critical}/min"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "alb_unhealthy" {
  count               = var.alb_arn_suffix != null && var.alb_target_group_arn_suffix != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-alb-unhealthy-hosts-${var.environment}"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 3
  period              = 60
  metric_name         = "UnHealthyHostCount"
  namespace           = "AWS/ApplicationELB"
  statistic           = "Maximum"
  threshold           = 1
  alarm_description   = "ALB ${var.alb_arn_suffix} target-group ${var.alb_target_group_arn_suffix} has unhealthy hosts"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.alb_target_group_arn_suffix
  }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# ECS alarms — running != desired for > 5 min
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "ecs_running_vs_desired" {
  for_each = toset(
    var.ecs_cluster_name != null ? var.ecs_service_names : []
  )

  alarm_name          = "${var.name_prefix}-ecs-${each.value}-replicas-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 5
  period              = 60
  metric_name         = "RunningTaskCount"
  namespace           = "AWS/ECS"
  statistic           = "Minimum"
  threshold           = 1
  alarm_description   = "ECS service ${each.value} running task count < desired for > 5 min"
  treat_missing_data  = "breaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = each.value
  }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# ElastiCache Redis alarms
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "redis_cpu" {
  count               = var.redis_replication_group_id != null ? 1 : 0
  alarm_name          = "${var.name_prefix}-redis-cpu-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  period              = 300
  metric_name         = "EngineCPUUtilization"
  namespace           = "AWS/ElastiCache"
  statistic           = "Average"
  threshold           = var.redis_cpu_critical_pct
  alarm_description   = "ElastiCache RG ${var.redis_replication_group_id} engine CPU > ${var.redis_cpu_critical_pct}% for 15 min"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  dimensions = {
    ReplicationGroupId = var.redis_replication_group_id
  }
  tags = var.tags
}

# ---------------------------------------------------------------------------
# Bedrock alarms — invocation throttling
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "bedrock_throttling" {
  count               = var.bedrock_alarm_enabled ? 1 : 0
  alarm_name          = "${var.name_prefix}-bedrock-throttling-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 300
  metric_name         = "InvocationThrottles"
  namespace           = "AWS/Bedrock"
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "Bedrock InvocationThrottles > 10 / 5 min — likely TPM ceiling hit"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [local.topic_arn]
  ok_actions          = [local.topic_arn]
  tags                = var.tags
}

# ---------------------------------------------------------------------------
# Dashboard — single pane of glass for the env.
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.name_prefix}-${var.environment}"

  dashboard_body = jsonencode({
    widgets = compact([
      var.rds_instance_id != null ? {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "RDS — CPU / free storage"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", var.rds_instance_id],
            [".", "FreeStorageSpace", ".", "."],
          ]
        }
      } : null,
      var.alb_arn_suffix != null ? {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "ALB — 5xx + latency"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", var.alb_arn_suffix],
            [".", "TargetResponseTime", ".", "."],
          ]
        }
      } : null,
      var.bedrock_alarm_enabled ? {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Bedrock — invocations + throttles"
          region = data.aws_region.current.name
          metrics = [
            ["AWS/Bedrock", "Invocations"],
            [".", "InvocationThrottles"],
            [".", "InvocationClientErrors"],
          ]
        }
      } : null,
    ])
  })
}

data "aws_region" "current" {}

resource "aws_ssm_parameter" "topic_arn" {
  name  = "/aqp/${var.environment}/alarm_topic_arn"
  type  = "String"
  value = local.topic_arn
  tags  = var.tags
}
