# Bedrock Proxy Gateway Infrastructure

Terraform infrastructure for deploying the Bedrock Proxy Gateway across central and shared AWS accounts.

## Architecture

### Multi-Account Design

- **Central Account**: Hosts ALB, ECS, VPC endpoints, CloudWatch Logs, consolidated guardrail configuration
- **Shared Account(s)**: Host Bedrock guardrails, IAM roles, write guardrails to central SSM registry

### Guardrail Consolidation

Each shared account writes its guardrails to central account SSM:

```
/bedrock-proxy-gateway/{env}/guardrails/account/{account-id}
```

Consolidation module reads all account registries and merges into:

```
/bedrock-proxy-gateway/{env}/guardrails/consolidated-config
```

## Prerequisites

1. Configure AWS profiles in `~/.aws/credentials`:

```ini
[central-prod]
aws_access_key_id = YOUR_CENTRAL_ACCOUNT_KEY
aws_secret_access_key = YOUR_CENTRAL_ACCOUNT_SECRET

[shared-account-1]
aws_access_key_id = YOUR_SHARED_ACCOUNT_KEY
aws_secret_access_key = YOUR_SHARED_ACCOUNT_SECRET
```

1. Run setup script to create S3 backend:

```bash
../scripts/setup.sh dev central-prod shared-account-1
```

## Deployment

### Using Scripts (Recommended)

For single or multiple shared accounts:

```bash
# Single shared account
../scripts/deploy.sh dev --apply \
  --central-profile central-prod \
  --shared-profiles shared-account-1

# Multiple shared accounts
../scripts/deploy.sh test --apply \
  --central-profile central-prod \
  --shared-profiles "shared-1,shared-2,shared-3"
```

### Manual Deployment

```bash
# Initialize
terraform init -backend-config=backend-dev.tfbackend

# Plan
terraform plan -var-file=dev.tfvars \
  -var="central_account_profile=central-prod" \
  -var="shared_account_profile=shared-account-1"

# Apply
terraform apply -var-file=dev.tfvars \
  -var="central_account_profile=central-prod" \
  -var="shared_account_profile=shared-account-1"
```

## Configuration Files

- `dev.tfvars` - Development environment configuration
- `test.tfvars` - Test environment configuration
- `backend-dev.tfbackend` - Dev S3 backend configuration
- `backend-test.tfbackend` - Test S3 backend configuration

## Modules

- `central_account/` - Central infrastructure (ALB, ECS, VPC, CloudWatch)
- `shared_account/` - Shared account resources (Bedrock, IAM, guardrails)
- `guardrail_consolidation/` - Merges guardrail registries from all shared accounts

## State Management

- S3 backend with native file locking (no DynamoDB)
- Separate state files per environment
- State stored in central account

## Outputs

Key outputs after deployment:

```bash
terraform output
```

- `ecs_alb_dns_name` - ALB DNS name for API access
