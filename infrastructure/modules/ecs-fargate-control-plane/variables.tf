variable "environment" {
  type        = string
  description = "Deployment environment (dev | staging | prod)."
}

variable "name_prefix" {
  type        = string
  default     = "aqp"
  description = "Resource-name prefix."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Common tags."
}

variable "vpc_id" {
  type        = string
  description = "VPC the Fargate tasks run in."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets across the VPC's AZs for awsvpc tasks."
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "CMK ARN for CloudWatch log group encryption."
}

variable "alb_security_group_id" {
  type        = string
  description = "ALB security group id (from modules/alb.security_group_id)."
}

variable "log_retention_days" {
  type        = number
  default     = 30
  description = "CloudWatch Logs retention for each service."
}

variable "adot_collector_image" {
  type        = string
  default     = "public.ecr.aws/aws-observability/aws-otel-collector:latest"
  description = "ADOT collector image — pin to a SHA in prod."
}

variable "adot_config_yaml" {
  type        = string
  default     = ""
  description = "Inline ADOT collector config (YAML). Empty uses the image default."
}

variable "secret_arns_for_tasks" {
  type        = list(string)
  default     = []
  description = "Secrets Manager ARNs the execution role can read for env injection."
}

variable "services" {
  type = map(object({
    image                   = string
    cpu                     = number
    memory                  = number
    desired_count           = number
    ports                   = list(number)
    cpu_architecture        = string
    task_role_policy_arns   = list(string)
    secrets                 = list(object({ name = string, valueFrom = string }))
    alb_target_group_arn    = string
  }))
  default = {
    admin = {
      image                   = "PLACEHOLDER-aqp-admin"
      cpu                     = 1024
      memory                  = 2048
      desired_count           = 2
      ports                   = [8000]
      cpu_architecture        = "ARM64"
      task_role_policy_arns   = []
      secrets                 = []
      alb_target_group_arn    = null
    }
    agentcore_proxy = {
      image                   = "PLACEHOLDER-aqp-agentcore-proxy"
      cpu                     = 512
      memory                  = 1024
      desired_count           = 2
      ports                   = [9000]
      cpu_architecture        = "ARM64"
      task_role_policy_arns   = []
      secrets                 = []
      alb_target_group_arn    = null
    }
  }
  description = "Per-service task definitions; the consumer composition overrides image + ARN wiring."
}
