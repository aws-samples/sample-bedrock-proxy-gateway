# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

variable "role_name" {
  description = "Name of the IAM role for the OIDC provider"
  type        = string
}

variable "aws_account_id" {
  description = "AWS Account ID"
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the OIDC provider"
  type        = string
}

variable "oidc_provider_url" {
  description = "URL of the OIDC provider"
  type        = string
}

variable "jwt_audience" {
  description = "JWT audience for OIDC provider"
  type        = string
  default     = "BPG"
}

variable "tags" {
  description = "Tags to apply to resources"
  type        = map(string)
  default     = {}
}

variable "allowed_source_vpc_endpoint_ids" {
  description = "ID of the source VPC endpoint allowed to use IAM role credentials"
  type        = list(string)
  default     = null # Please consider to make this value mandatory for production (remove condition from the policy, and fail deployment if null)
}

variable "restricted_role_session_name_suffix" {
  description = "Suffix to append to a role session name to restrict ARWWI calls with JWT"
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment name"
  type        = string
}
