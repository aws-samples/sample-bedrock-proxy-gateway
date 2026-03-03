# OIDC Identity Federation Module
module "oidc_federation" {
  source = "./oidc_federation"

  oauth_provider_url = var.oauth_provider_url
  jwt_audience       = var.jwt_audience
  tags               = var.common_tags
}

# IAM Role Module
module "iam_role" {
  source = "./iam_role"

  role_name                           = var.oidc_role_name
  aws_account_id                      = var.common.aws_account_id
  oidc_provider_arn                   = local.oauth_provider_arn
  oidc_provider_url                   = local.oauth_provider_url_parsed
  jwt_audience                        = var.jwt_audience
  tags                                = var.common_tags
  allowed_source_vpc_endpoint_ids     = local.allowed_source_vpc_endpoint_ids != [] ? local.allowed_source_vpc_endpoint_ids : null
  restricted_role_session_name_suffix = var.restricted_role_session_name_suffix
  environment                         = var.common.environment

  depends_on = [
    module.oidc_federation
  ]
}

# CloudWatch KMS Module
module "cloudwatch_kms" {
  source = "./cloudwatch_kms"

  aws_account_id     = var.common.aws_account_id
  central_account_id = var.central_account_id
  kms_alias_name     = "alias/${var.common.environment}-bedrock-logs-key"
  log_group_name     = "/aws/bedrock/modelinvocations"
  log_retention_days = var.common.log_retention_days
  tags               = var.common_tags

  depends_on = [
    module.oidc_federation,
    module.iam_role
  ]
}

# Bedrock Guardrails Module
module "bedrock_guardrails" {
  source = "./bedrock_guardrails"
  providers = {
    aws         = aws
    aws.central = aws.central
  }

  common                      = var.common
  tags                        = var.common_tags
  bedrock_logging_role_name   = local.bedrock_logging_role
  bedrock_logging_policy_name = local.bedrock_logging_policy
  log_group_name              = "/aws/bedrock/modelinvocations"
  central_account_id          = var.central_account_id

  depends_on = [
    module.oidc_federation,
    module.iam_role,
    module.cloudwatch_kms
  ]
}

# Logging Module - Forward logs to central account Kinesis stream
module "logging" {
  source             = "./logging"
  filter_role_name   = module.iam_role.role_name
  central_account_id = var.central_account_id
  common             = var.common
  common_tags        = var.common_tags

  depends_on = [
    module.oidc_federation,
    module.iam_role,
    module.cloudwatch_kms,
    module.bedrock_guardrails
  ]
}
