

variable "filter_role_name" {
  type        = string
  description = "ARN of the IAM role to filter Bedrock logs by (only logs from this role will be forwarded)"
}

variable "central_account_id" {
  type        = string
  description = "Central account ID for cross-account resource access"
}

variable "common" {
  type = object({
    app_id             = string
    aws_region         = string
    aws_account_id     = string
    environment        = string
    service_name       = string
    log_retention_days = number
  })
  description = "Common variables shared across all modules"
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}
