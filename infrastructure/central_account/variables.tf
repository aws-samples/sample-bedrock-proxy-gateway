# =============================================================================
# DNS AND CERTIFICATE VARIABLES
# =============================================================================

variable "mtls_cert_ca_s3_path" {
  description = "S3 URI path to the mTLS CA certificate"
  type        = string
  default     = ""
}

variable "shared_account_ids" {
  description = "List of shared account IDs for resource access"
  type        = string
}

variable "oidc_role_name" {
  description = "Name of the IAM role for the OIDC provider"
  type        = string
}
# =============================================================================
# CONTAINER CONFIGURATION
# =============================================================================

variable "ecs_task_cpu" {
  description = "CPU units for ECS task (from environment config)"
  type        = number
}

variable "ecs_task_memory" {
  description = "Memory for ECS task in MiB (from environment config)"
  type        = number
}

variable "ecs_service_desired_count" {
  description = "Desired number of ECS tasks (from environment config)"
  type        = number
}

variable "log_retention" {
  description = "Log retention (from environment config)"
  type        = number
}

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

variable "gw_api_image_tag" {
  type        = string
  description = "Docker image tag for the Bedrock Gateway API to deploy"
}

# =============================================================================
# OAUTH/JWT CONFIGURATION
# =============================================================================
variable "oauth_jwks_url" {
  type        = string
  description = "OAuth JWKS URL for JWT token validation (e.g., https://<tenant>.auth0.com/.well-known/jwks.json)"
}

variable "oauth_issuer" {
  type        = string
  description = "OAuth token issuer (e.g., https://<tenant>.auth0.com/)"
}

variable "jwt_audience" {
  type        = string
  description = "Expected JWT audience claim (must match aud in tokens)"
}

variable "jwt_allowed_scopes" {
  type        = string
  description = "Comma-separated list of allowed JWT scopes (e.g., bedrockproxygateway:read,bedrockproxygateway:invoke,bedrockproxygateway:admin)"
}
