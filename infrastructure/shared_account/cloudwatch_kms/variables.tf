variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "central_account_id" {
  description = "Central AWS Account ID"
  type        = string
}

variable "kms_alias_name" {
  description = "Alias name for the KMS key"
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group name"
  type        = string
}

variable "log_retention_days" {
  description = "Log retention period in days"
  type        = number
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}
