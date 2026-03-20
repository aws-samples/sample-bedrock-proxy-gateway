# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

variable "common" {
  type = object({
    app_id             = string
    aws_region         = string
    aws_account_id     = string
    environment        = string
    service_name       = string
    log_retention_days = number
  })
  description = "Common variables shared across all modules"
}

variable "tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}

variable "bedrock_logging_role_name" {
  description = "Name of the Bedrock logging IAM role"
  type        = string
}

variable "bedrock_logging_policy_name" {
  description = "Name of the Bedrock logging IAM policy"
  type        = string
}

variable "log_group_name" {
  description = "CloudWatch log group name for Bedrock"
  type        = string
}

variable "central_account_id" {
  description = "Central account ID where logs are aggregated"
  type        = string
}
