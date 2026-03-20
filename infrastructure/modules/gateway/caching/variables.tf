# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# NETWORK INFRASTRUCTURE VARIABLES
# =============================================================================

variable "vpc_id" {
  description = "VPC ID where resources will be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs for resource deployment"
  type        = list(string)
}

# =============================================================================
# SHARED CONFIGURATION OBJECTS
# =============================================================================

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

variable "common_tags" {
  type        = map(string)
  description = "Common tags applied to all resources"
}

variable "vpc_cidr_block" {
  type        = string
  description = "VPC CIDR block for security group rules"
}
