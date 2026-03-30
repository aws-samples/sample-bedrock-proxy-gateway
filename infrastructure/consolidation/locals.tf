# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

data "aws_caller_identity" "current" {}

locals {
  common = {
    app_id         = var.app_id
    aws_region     = var.aws_region
    aws_account_id = data.aws_caller_identity.current.account_id
    environment    = var.environment
    service_name   = var.service_name
  }

  common_tags = merge({
    Environment = var.environment
    Service     = var.service_name
    ManagedBy   = "Bedrock Proxy Gateway Terraform"
    AppId       = var.app_id
  }, var.additional_tags)
}
