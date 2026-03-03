# =============================================================================
# ALB INTEGRATION VARIABLES
# =============================================================================

variable "alb_target_group_arn" {
  description = "ALB target group ARN from networking module"
  type        = string
}

variable "alb_security_group_id" {
  description = "ALB security group ID from networking module"
  type        = string
}

variable "bedrock_runtime_vpc_endpoint_dns" {
  description = "Bedrock VPC Endpoint DNS name"
  type        = string
  default     = ""
}

variable "sts_vpc_endpoint_dns" {
  description = "STS VPC Endpoint DNS name"
  type        = string
  default     = ""
}

# =============================================================================
# NETWORK INFRASTRUCTURE VARIABLES
# =============================================================================

variable "vpc_id" {
  description = "VPC ID where resources will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for resource deployment"
  type        = list(string)
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

variable "environment_config" {
  type = object({
    log_retention             = number
    ecs_task_cpu              = number
    ecs_task_memory           = number
    ecs_service_desired_count = number
  })
  description = "Environment-specific configuration from root variables"
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}

variable "gw_api_image_tag" {
  type        = string
  description = "Docker image tag for the Bedrock Gateway API to deploy"
}

variable "observability_policy_arn" {
  type        = string
  description = "ARN of the observability access policy"
  default     = ""
}

variable "s3_bucket_name" {
  type        = string
  description = "Name of the observability S3 bucket"
  default     = ""
}

variable "valkey_endpoint_address" {
  type        = string
  description = "Valkey cache endpoint address"
  default     = ""
}

variable "valkey_endpoint_port" {
  type        = string
  description = "Valkey cache endpoint port"
  default     = ""
}

variable "vpc_cidr_block" {
  type        = string
  description = "VPC CIDR block for security group rules"
}


# =============================================================================
# OAUTH/JWT CONFIGURATION VARIABLES
# =============================================================================

variable "oauth_jwks_url" {
  type        = string
  description = "OAuth JWKS URL for JWT token validation"
}

variable "oauth_issuer" {
  type        = string
  description = "OAuth token issuer"
}

variable "jwt_audience" {
  type        = string
  description = "Expected JWT audience claim"
}

variable "jwt_allowed_scopes" {
  type        = string
  description = "Comma-separated list of allowed JWT scopes"
}
