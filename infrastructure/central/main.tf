# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

module "central_account" {
  source = "../modules/gateway"

  mtls_cert_ca_s3_path      = var.mtls_cert_ca_s3_path
  ecs_task_cpu              = local.env_config.ecs_cpu
  ecs_task_memory           = local.env_config.ecs_memory
  ecs_service_desired_count = local.env_config.ecs_desired_count
  log_retention             = local.env_config.log_retention
  oidc_role_name            = local.oidc_role_name
  shared_account_ids        = var.shared_account_ids
  common                    = local.common
  common_tags               = local.common_tags
  gw_api_image_tag          = var.gw_api_image_tag
  oauth_jwks_url            = var.oauth_jwks_url
  oauth_issuer              = var.oauth_issuer
  jwt_audience              = var.jwt_audience
  jwt_allowed_scopes        = var.jwt_allowed_scopes
}

# Write VPC endpoint IDs to SSM so shared accounts can read them
resource "aws_ssm_parameter" "bedrock_vpce_id" {
  name  = "/${var.service_name}/${var.environment}/central/bedrock-vpce-id"
  type  = "String"
  value = module.central_account.bedrock_vpc_endpoint
}

resource "aws_ssm_parameter" "bedrock_runtime_vpce_id" {
  name  = "/${var.service_name}/${var.environment}/central/bedrock-runtime-vpce-id"
  type  = "String"
  value = module.central_account.bedrock_runtime_vpc_endpoint
}
