# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

module "shared_account" {
  source = "../modules/bedrock_access"
  providers = {
    aws         = aws
    aws.central = aws.central
  }

  common      = local.common
  common_tags = local.common_tags

  oidc_role_name     = local.oidc_role_name
  oauth_provider_url = var.oauth_issuer
  jwt_audience       = var.jwt_audience
  central_account_id = var.central_account_id

  bedrock_vpce_id         = data.aws_ssm_parameter.bedrock_vpce_id.value
  bedrock_runtime_vpce_id = data.aws_ssm_parameter.bedrock_runtime_vpce_id.value

  restricted_role_session_name_suffix = var.restricted_role_session_name_suffix
}
