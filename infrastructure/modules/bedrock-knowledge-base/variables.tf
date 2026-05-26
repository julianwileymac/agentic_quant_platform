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

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "Optional CMK ARN for KB S3 bucket encryption."
}

variable "oss_collection_arn" {
  type        = string
  description = "OpenSearch Serverless VECTORSEARCH collection ARN (from modules/opensearch-serverless)."
}

variable "oss_collection_name" {
  type        = string
  description = "OpenSearch Serverless VECTORSEARCH collection name."
}

variable "embedding_model_arn" {
  type        = string
  default     = "arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0"
  description = "Foundation-model ARN used to embed source documents."
}

variable "settle_resource_dep" {
  type        = string
  default     = null
  description = "Optional reference to modules/opensearch-serverless's settle resource id (eventual-consistency guard)."
}
