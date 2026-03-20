# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

locals {
  # Construct the base name prefix using environment and AppId
  name_prefix = "${var.common.app_id}-${var.common.environment}"

  # Create the final resource name by combining prefix and service
  resource_name = "${local.name_prefix}-${var.common_tags["Service"]}"

  # ALB resource names
  alb_name                = "alb-${local.name_prefix}"
  alb_target_group_name   = "tg-${local.name_prefix}"
  alb_security_group_name = "sec-gp-${local.resource_name}-alb"
  alb_s3_bucket_name      = "s3-${local.resource_name}-${var.common.aws_account_id}-alb-logs"
}
