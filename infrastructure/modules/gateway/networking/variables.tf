# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# DNS AND CERTIFICATE VARIABLES
# =============================================================================

variable "mtls_cert_ca_s3_path" {
  description = "S3 URI path to the mTLS CA certificate"
  type        = string
  default     = ""
}

# =============================================================================
# SHARED ACCOUNT CONFIGURATION
# =============================================================================

variable "shared_account_ids" {
  description = "List of shared account IDs for resource access"
  type        = string
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
