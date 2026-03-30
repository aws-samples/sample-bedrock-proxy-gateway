# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

locals {
  # Construct the base name prefix using environment and AppId
  name_prefix = "${var.common.app_id}-${var.common.environment}"

  # Create the final resource name by combining prefix and service
  resource_name = local.name_prefix

  # Elasticache resource names
  cache_name = "vlk-${local.resource_name}"

  # Security group names
  cache_security_group_name = "sec-gp-${local.resource_name}-sts-cache"

}
