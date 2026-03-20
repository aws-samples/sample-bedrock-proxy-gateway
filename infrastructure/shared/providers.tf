# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

terraform {
  required_version = ">=1.12.2, <2.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>6.0.0"
    }
  }
  backend "s3" {}
}

# Shared account provider (default)
provider "aws" {
  region  = var.aws_region
  profile = var.shared_account_profile
}

# Central account provider (for cross-account SSM writes)
provider "aws" {
  alias   = "central"
  region  = var.aws_region
  profile = var.central_account_profile
}
