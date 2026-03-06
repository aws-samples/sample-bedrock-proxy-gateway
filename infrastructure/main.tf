# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

module "central_account" {
  source = "./central_account"
  providers = {
    aws = aws.central
  }

  # DNS and Certificates
  mtls_cert_ca_s3_path = var.mtls_cert_ca_s3_path

  # ECS Configuration
  ecs_task_cpu              = local.env_config.ecs_cpu
  ecs_task_memory           = local.env_config.ecs_memory
  ecs_service_desired_count = local.env_config.ecs_desired_count
  log_retention             = local.env_config.log_retention
  oidc_role_name            = local.oidc_role_name
  shared_account_ids        = var.shared_account_ids

  # Shared Configuration
  common           = local.common
  common_tags      = local.common_tags
  gw_api_image_tag = var.gw_api_image_tag

  # Centralised Monitoring

  # OAuth/JWT Configuration
  oauth_jwks_url     = var.oauth_jwks_url
  oauth_issuer       = var.oauth_issuer
  jwt_audience       = var.jwt_audience
  jwt_allowed_scopes = var.jwt_allowed_scopes
}

module "shared_account" {
  source = "./shared_account"
  providers = {
    aws         = aws.shared
    aws.central = aws.central
  }

  # Shared Configuration
  common      = local.common
  common_tags = local.common_tags

  oidc_role_name     = local.oidc_role_name
  oauth_provider_url = var.oauth_issuer
  jwt_audience       = var.jwt_audience
  central_account_id = var.central_account_id

  bedrock_vpce_id         = module.central_account.bedrock_vpc_endpoint
  bedrock_runtime_vpce_id = module.central_account.bedrock_runtime_vpc_endpoint

  restricted_role_session_name_suffix = var.restricted_role_session_name_suffix
}

# Guardrail Consolidation Module - Runs after shared accounts are deployed
module "guardrail_consolidation" {
  source = "./guardrail_consolidation"
  providers = {
    aws = aws.central
  }

  # Shared Configuration
  common      = local.common
  common_tags = local.common_tags

  depends_on = [
    module.central_account,
    module.shared_account
  ]
}
