variable "environment" {
  type        = string
  description = "Deployment environment (dev | staging | prod)."
}

variable "name_prefix" {
  type        = string
  default     = "aqp"
  description = "Resource-name prefix; concatenated with environment + role."
}

variable "tags" {
  type        = map(string)
  default     = {}
  description = "Common tags applied to every resource."
}

variable "vpc_id" {
  type        = string
  description = "VPC the AgentCore Runtime ENIs attach to."
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnets the AgentCore Runtime is reachable from."
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "Optional CMK ARN for log group encryption."
}

variable "runtime_image_uri" {
  type        = string
  description = "Fully-qualified ARM64 OCI image URI from ECR for the agent runtime."
}

variable "memory_event_expiry_days" {
  type        = number
  default     = 90
  description = "Retention for AgentCore Memory short-term events."
}

variable "gateway_authorizer_type" {
  type        = string
  default     = "CUSTOM_JWT"
  description = "AgentCore Gateway authorizer type — CUSTOM_JWT | NONE."
}

variable "allowed_model_arns" {
  type = list(string)
  default = [
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-*",
    "arn:aws:bedrock:*::foundation-model/anthropic.claude-haiku-4-5-*",
    "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0",
  ]
  description = "IAM allow-list for bedrock:InvokeModel."
}

variable "broker_secret_arns" {
  type        = list(string)
  default     = []
  description = "Secrets Manager ARNs the AgentCore Runtime may read."
}

variable "kb_source_bucket_arn" {
  type        = string
  default     = null
  description = "Optional S3 KB source bucket; grants GetObject/ListBucket."
}
