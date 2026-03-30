# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

module "container_insights" {
  source      = "./container_insights"
  common      = var.common
  common_tags = var.common_tags
}

module "networking" {
  source               = "./networking"
  mtls_cert_ca_s3_path = var.mtls_cert_ca_s3_path
  shared_account_ids   = var.shared_account_ids
  common               = var.common
  common_tags          = var.common_tags
}

module "waf" {
  source      = "./waf"
  common      = var.common
  common_tags = var.common_tags
  alb_arn     = module.networking.ecs_alb_arn
}

module "observability" {
  source             = "./observability"
  common             = var.common
  common_tags        = var.common_tags
  shared_account_ids = var.shared_account_ids
}

module "compute" {
  source                           = "./compute"
  alb_target_group_arn             = module.networking.ecs_alb_target_group_arn
  alb_security_group_id            = module.networking.ecs_alb_security_group_id
  bedrock_runtime_vpc_endpoint_dns = module.networking.bedrock_runtime_vpc_endpoint_dns
  sts_vpc_endpoint_dns             = module.networking.sts_vpc_endpoint_dns
  vpc_id                           = module.networking.vpc_id
  private_subnet_ids               = module.networking.private_subnet_ids
  environment_config = {
    log_retention             = var.log_retention
    ecs_task_cpu              = var.ecs_task_cpu
    ecs_task_memory           = var.ecs_task_memory
    ecs_service_desired_count = var.ecs_service_desired_count
  }
  common             = var.common
  common_tags        = var.common_tags
  gw_api_image_tag   = var.gw_api_image_tag
  shared_account_ids = var.shared_account_ids
  oidc_role_name     = var.oidc_role_name

  observability_policy_arn = module.observability.observability_policy_arn
  s3_bucket_name           = module.observability.s3_bucket_name
  valkey_endpoint_address  = module.caching.valkey_endpoint[0].address
  valkey_endpoint_port     = tostring(module.caching.valkey_endpoint[0].port)
  vpc_cidr_block           = module.networking.vpc_cidr_block

  oauth_jwks_url     = var.oauth_jwks_url
  oauth_issuer       = var.oauth_issuer
  jwt_audience       = var.jwt_audience
  jwt_allowed_scopes = var.jwt_allowed_scopes
}

module "caching" {
  source             = "./caching"
  vpc_id             = module.networking.vpc_id
  private_subnet_ids = module.networking.private_subnet_ids
  common             = var.common
  common_tags        = var.common_tags
  vpc_cidr_block     = module.networking.vpc_cidr_block
}
