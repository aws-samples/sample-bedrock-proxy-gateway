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

provider "aws" {
  region  = var.aws_region
  profile = var.central_account_profile
}
