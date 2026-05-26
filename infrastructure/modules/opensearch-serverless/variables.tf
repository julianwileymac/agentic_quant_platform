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
  description = "Common tags applied to every resource."
}

variable "collection_suffix" {
  type        = string
  default     = "kb-collection"
  description = "Suffix appended to the collection name."
}

variable "kms_key_arn" {
  type        = string
  default     = null
  description = "Optional CMK ARN for collection encryption."
}

variable "public_dashboard" {
  type        = bool
  default     = false
  description = "Allow public access to the OSS dashboard (almost always false)."
}

variable "public_collection" {
  type        = bool
  default     = false
  description = "Allow public access to the collection (almost always false)."
}

variable "settle_duration" {
  type        = string
  default     = "20s"
  description = "How long to wait after collection creation for IAM propagation."
}
