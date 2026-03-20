# Guardrail Consolidation Module

## Overview

This module consolidates guardrail configurations from multiple shared accounts and stores them in the central account's SSM Parameter Store. It runs after both central and shared account deployments are complete.

## Deployment Order

1. **Central Account** - Creates Kinesis streams and other central resources
2. **Shared Account(s)** - Creates guardrails and integrates with central Kinesis
3. **Guardrail Consolidation** - Consolidates guardrail configs and updates central SSM

## Environment Support

- **dev/feature**: Single account deployment (central = shared)
- **qa/preprod**: One central account + one shared account
- **prod**: One central account + multiple shared accounts (up to 10)

## How It Works

### Multi-Account Environments (qa, preprod, prod)

- Assumes IAM role in each shared account to access Terraform state
- Reads terraform remote state from each shared account's S3 bucket
- Extracts guardrail configurations from `bedrock_guardrails` output
- Consolidates all guardrails by logical ID across accounts
- Stores consolidated config in central account SSM

### Single Account Environments (dev, feature)

- Uses provided `shared_account_guardrails` variable
- Consolidates guardrails from the variable input
- Stores consolidated config in SSM

## Prerequisites for Multi-Account

Each shared account must have an IAM role (default: `TerraformStateAccessRole`) with:
- Trust relationship allowing the central account to assume it
- Permissions to read from the Terraform state S3 bucket

## Usage

```hcl
module "guardrail_consolidation" {
  source = "./guardrail_consolidation"

  common                    = var.common
  common_tags              = var.common_tags
  shared_account_ids       = var.shared_account_ids
  shared_account_guardrails = var.shared_account_guardrails
  cross_account_role_name  = "TerraformStateAccessRole"  # optional
}
```

## Outputs

- `consolidated_guardrails_ssm_parameter`: SSM parameter name
- `consolidated_guardrails_config`: The consolidated configuration object
