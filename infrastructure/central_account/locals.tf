# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

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
}
