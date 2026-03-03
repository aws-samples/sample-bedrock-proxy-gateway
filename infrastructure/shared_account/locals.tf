locals {
  # Access tags
  app_id       = var.common.app_id
  service_name = var.common.service_name

  # Access common variables
  aws_region         = var.common.aws_region
  environment        = var.common.environment
  log_retention_days = var.common.log_retention_days

  # You can also create additional computed locals if needed
  name_prefix   = "${local.environment}-${local.app_id}"
  resource_name = "${local.name_prefix}-${local.service_name}"

  # OAuth provider configuration
  # For trust policy condition key, keep the trailing slash to match OIDC provider URL
  oauth_provider_url_parsed = trimprefix(var.oauth_provider_url, "https://")
  oauth_provider_arn        = "arn:aws:iam::${var.common.aws_account_id}:oidc-provider/${trimprefix(var.oauth_provider_url, "https://")}"

  # IAM Roles
  bedrock_logging_role   = "iam-rol-${local.resource_name}-bedrock-logs"
  bedrock_logging_policy = "iam-pol-${local.resource_name}-bedrock-policy"

  # List of VPC Endpoints allowed to leverage cross-account IAM role credentials (obtained via AssumeRoleWWI with OAuth token)
  allowed_source_vpc_endpoint_ids = [var.bedrock_vpce_id, var.bedrock_runtime_vpce_id]
}
