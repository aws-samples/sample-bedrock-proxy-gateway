# =============================================================================
# SHARED CONFIGURATION OBJECTS
# =============================================================================

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

variable "oidc_role_name" {
  description = "Name of the IAM role for the OIDC provider"
  type        = string
}

variable "jwt_audience" {
  description = "JWT audience for OIDC provider"
  type        = string
  default     = "BPG"
}

variable "oauth_provider_url" {
  description = "OAuth provider URL (e.g., 'https://your-oauth-provider.com')"
  type        = string
}

variable "central_account_id" {
  description = "List of central account ID for resource access"
  type        = string
}

variable "bedrock_vpce_id" {
  type        = string
  description = "Bedrock VPC Endpoint ID"
  default     = ""
}

variable "bedrock_runtime_vpce_id" {
  type        = string
  description = "Bedrock VPC Endpoint ID"
  default     = ""
}

variable "restricted_role_session_name_suffix" {
  description = "Suffix to append to a role session name to restrict ARWWI calls with JWT"
  type        = string
  default     = null
}
