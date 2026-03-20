# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

variable "app_id" {
  type    = string
  default = "myapp"
}

variable "service_name" {
  type    = string
  default = "bedrock-proxy-gateway"
}

variable "environment" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "central_account_profile" {
  type    = string
  default = "default"
}

# Accepted from shared tfvars but unused by this stage
variable "shared_account_ids" {
  type    = string
  default = ""
}

variable "central_account_id" {
  type    = string
  default = ""
}

variable "shared_account_profile" {
  type    = string
  default = "default"
}

variable "mtls_cert_ca_s3_path" {
  type    = string
  default = ""
}

variable "oauth_jwks_url" {
  type    = string
  default = ""
}

variable "oauth_issuer" {
  type    = string
  default = ""
}

variable "jwt_audience" {
  type    = string
  default = ""
}

variable "jwt_allowed_scopes" {
  type    = string
  default = ""
}

variable "restricted_role_session_name_suffix" {
  type    = string
  default = null
}

variable "gw_api_image_tag" {
  type    = string
  default = ""
}

variable "additional_tags" {
  type    = map(string)
  default = {}
}

variable "environment_config" {
  type = map(object({
    ecs_desired_count = number
    ecs_cpu           = number
    ecs_memory        = number
    domain_prefix     = string
    log_retention     = number
  }))
  default = {
    dev  = { ecs_desired_count = 1, ecs_cpu = 2048, ecs_memory = 4096, domain_prefix = "dev", log_retention = 7 }
    test = { ecs_desired_count = 4, ecs_cpu = 4096, ecs_memory = 8192, domain_prefix = "test", log_retention = 120 }
  }
}
