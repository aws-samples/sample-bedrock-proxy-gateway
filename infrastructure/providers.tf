terraform {
  required_version = ">=1.12.2, <2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~>6.0.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~>3.0"
    }
  }

  backend "s3" {}
}

# Default provider (required by Terraform)
provider "aws" {
  region  = var.aws_region
  profile = var.central_account_profile
}

provider "aws" {
  alias   = "central"
  region  = var.aws_region
  profile = var.central_account_profile
}

provider "aws" {
  alias   = "shared"
  region  = var.aws_region
  profile = var.shared_account_profile
}
