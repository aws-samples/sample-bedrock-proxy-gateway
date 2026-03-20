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
  description = "Common tags applied to all resources"
  type        = map(string)
}

variable "kms_key_arn" {
  description = "ARN of the KMS key to use for SSM parameter encryption"
  type        = string
}
