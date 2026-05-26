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
  default     = null
  description = "Unused (SFN + EventBridge are regional managed services); kept for uniform contract."
}

variable "private_subnet_ids" {
  type        = list(string)
  default     = []
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "CMK ARN for log group encryption."
}

variable "log_retention_days" {
  type        = number
  default     = 90
  description = "CloudWatch Logs retention for the SFN log group."
}

variable "state_machine_definition_json" {
  type        = string
  description = "Step Function definition JSON (consumer renders from configs/strategies/)."
}

variable "backend_lambda_arns" {
  type        = list(string)
  default     = []
  description = "Lambda ARNs the SFN is allowed to InvokeFunction on."
}

variable "nightly_cron_expression" {
  type        = string
  default     = "cron(0 21 ? * MON-FRI *)"
  description = "EventBridge schedule expression — defaults to 21:00 UTC weekdays."
}

variable "kb_source_bucket_name" {
  type        = string
  default     = null
  description = "Optional S3 source bucket to trigger KB re-ingestion on PutObject."
}

variable "kb_sync_lambda_arn" {
  type        = string
  default     = null
  description = "Optional Lambda ARN that calls bedrock-agent:StartIngestionJob on KB sync events."
}
