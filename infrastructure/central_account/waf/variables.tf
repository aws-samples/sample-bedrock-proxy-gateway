# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

variable "common" {
  type = object({
    app_id         = string
    aws_region     = string
    aws_account_id = string
    environment    = string
    service_name   = string
  })
  description = "Common variables shared across all modules"
}

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}

variable "alb_arn" {
  description = "ARN of the ALB to associate with WAF"
  type        = string
}
