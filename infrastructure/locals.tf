# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# LOCAL VALUES AND COMPUTED VARIABLES
# =============================================================================

locals {
  # =============================================================================
  # ENVIRONMENT CONFIGURATION LOGIC
  # Handles both predefined environments and user workspaces
  # =============================================================================

  # Check if environment exists in predefined configs, otherwise use dev defaults for user workspaces
  env_config = contains(keys(var.environment_config), var.environment) ? var.environment_config[var.environment] : {
    ecs_desired_count = 1
    ecs_cpu           = 2048
    ecs_memory        = 4096
    domain_prefix     = var.environment # Uses workspace name as domain prefix
    log_retention     = 7
  }

  # =============================================================================
  # COMMON VARIABLES OBJECT
  # Shared across all modules for consistent configuration
  # =============================================================================
  common = {
    app_id             = var.app_id
    aws_region         = var.aws_region
    aws_account_id     = data.aws_caller_identity.current.account_id
    environment        = var.environment
    service_name       = var.service_name
    log_retention_days = local.env_config.log_retention
  }

  # =============================================================================
  # RESOURCE TAGGING
  # Consistent tagging strategy across all resources
  # =============================================================================
  common_tags = merge({
    Environment = var.environment
    Service     = var.service_name
    ManagedBy   = "Bedrock Proxy Gateway Terraform"
    AppId       = var.app_id
  }, var.additional_tags)

  # =============================================================================
  # CROSS-ACCOUNT LOGGING CONFIGURATION
  # For multi-account deployments
  # =============================================================================
  name_prefix    = "${var.environment}-${var.app_id}"
  resource_name  = "${local.name_prefix}-${var.service_name}"
  oidc_role_name = "iam-rol-${local.resource_name}-oidc"
}
