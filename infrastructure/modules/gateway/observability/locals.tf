# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

locals {
  # Construct the base name prefix using environment and AppId
  name_prefix = "${var.common.app_id}-${var.common.environment}"

  # Create the final resource name by combining prefix and service
  resource_name = "${local.name_prefix}-${var.common.service_name}"

  # S3 bucket name with account ID, region, environment, service and signal suffix
  s3_bucket_name = "s3-${var.common.aws_account_id}-${var.common.aws_region}-${var.common.app_id}-${var.common.environment}-observability"

  # Kinesis stream names with appropriate suffixes

  # KMS resource names
  kms_alias_name = "alias/${local.resource_name}-observability"

  # IAM policy name
  observability_access_policy_name = "iam-pol-${local.resource_name}-observability-access"
}
