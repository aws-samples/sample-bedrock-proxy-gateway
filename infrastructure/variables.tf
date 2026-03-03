# =============================================================================
# CORE APPLICATION VARIABLES
# =============================================================================

variable "app_id" {
  description = "Application ID in lowercase"
  type        = string
  default     = "myapp"
}

variable "service_name" {
  description = "Name of the service"
  type        = string
  default     = "bedrock-gateway"
}

variable "environment" {
  description = "Deployment environment (dev/test)"
  type        = string
}

variable "aws_region" {
  description = "AWS Region"
  type        = string
}

# =============================================================================
# ACCOUNT CONFIGURATION
# =============================================================================

variable "shared_account_ids" {
  description = "Comma-separated list of shared account IDs for resource access"
  type        = string
}

variable "central_account_id" {
  description = "Central account ID for resource access"
  type        = string
}

variable "central_account_profile" {
  description = "AWS profile for central account"
  type        = string
  default     = "default"
}

variable "shared_account_profile" {
  description = "AWS profile for shared account"
  type        = string
  default     = "default"
}

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================

variable "mtls_cert_ca_s3_path" {
  description = "S3 URI path to the mTLS CA certificate"
  type        = string
  default     = ""
}

variable "oauth_jwks_url" {
  description = "OAuth JWKS URL for JWT token validation"
  type        = string
  default     = ""
}

variable "oauth_issuer" {
  description = "OAuth token issuer"
  type        = string
  default     = ""
}

variable "jwt_audience" {
  description = "Expected JWT audience claim"
  type        = string
  default     = ""
}

variable "jwt_allowed_scopes" {
  description = "Comma-separated list of allowed JWT scopes"
  type        = string
  default     = "bedrockproxygateway:read,bedrockproxygateway:invoke,bedrockproxygateway:admin"
}

variable "restricted_role_session_name_suffix" {
  description = "Suffix to append to a role session name to restrict ARWWI calls with JWT"
  type        = string
  default     = null
}

# =============================================================================
# ENVIRONMENT-SPECIFIC CONFIGURATION
# =============================================================================

variable "environment_config" {
  description = "Environment-specific configuration for ECS and infrastructure"
  type = map(object({
    ecs_desired_count = number
    ecs_cpu           = number
    ecs_memory        = number
    domain_prefix     = string
    log_retention     = number
  }))
  default = {
    dev = {
      ecs_desired_count = 1
      ecs_cpu           = 2048
      ecs_memory        = 4096
      domain_prefix     = "dev"
      log_retention     = 7
    }
    test = {
      ecs_desired_count = 4
      ecs_cpu           = 4096
      ecs_memory        = 8192
      domain_prefix     = "test"
      log_retention     = 120
    }
  }
}

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

variable "gw_api_image_tag" {
  description = "Docker image tag for the Bedrock Gateway API to deploy"
  type        = string
  default     = ""
}

# =============================================================================
# TAGGING
# =============================================================================

variable "additional_tags" {
  description = "Additional tags to add to all resources"
  type        = map(string)
  default     = {}
}
