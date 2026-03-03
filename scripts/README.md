# Deployment Scripts

This directory contains scripts for setting up, deploying, and managing the Bedrock Proxy Gateway infrastructure.

## Scripts Overview

### setup.sh
Prepares the AWS environment for Terraform deployment by creating S3 buckets for state storage and backend configuration files.

**Usage:**
```bash
# Single account deployment (uses default AWS profile)
./setup.sh dev

# Multi-account deployment (specify profiles)
./setup.sh dev central-profile shared-profile
```

**Arguments:**
- `environment` (required): Environment name (dev, test)
- `central-profile` (optional): AWS profile for central account (default: "default")
- `shared-profile` (optional): AWS profile for shared account (default: "default")

**What it does:**
- Creates S3 bucket for Terraform state in central account
- Generates backend configuration file (`infrastructure/backend-{env}.tfbackend`)
- Installs required tools (UV, Terraform) based on OS

### deploy.sh
Deploys the infrastructure using Terraform.

**Usage:**
```bash
# Plan only (default)
./deploy.sh dev

# Plan with custom profiles (single shared account)
./deploy.sh dev --central-profile central-prod --shared-profiles shared-prod

# Plan with multiple shared accounts
./deploy.sh dev --central-profile central-prod --shared-profiles "shared-1,shared-2,shared-3"

# Apply changes
./deploy.sh dev --apply

# Apply with multiple shared accounts
./deploy.sh dev --apply \
  --central-profile central-prod \
  --shared-profiles "shared-1,shared-2,shared-3"
```

**Arguments:**
- `environment` (required): Environment name (dev, test)
- `--apply`: Apply changes (default is plan only)
- `--central-profile`: AWS profile for central account (default: "default")
- `--shared-profiles`: Comma-separated AWS profiles for shared accounts (default: "default")

**What it does:**
- Runs infrastructure setup script
- Builds and pushes Docker images to ECR (in central account)
- Initializes Terraform with backend configuration
- Deploys to each shared account sequentially:
  - Each shared account writes its guardrails to central SSM registry
- Runs final consolidation to merge all guardrail registries
- Plans/applies infrastructure changes for each shared account

### destroy.sh
Destroys the infrastructure.

**Usage:**
```bash
# Interactive confirmation
./destroy.sh dev

# With custom profiles (single shared account)
./destroy.sh dev --central-profile central-prod --shared-profiles shared-prod

# With multiple shared accounts
./destroy.sh dev \
  --central-profile central-prod \
  --shared-profiles "shared-1,shared-2,shared-3"

# Skip confirmation prompt
./destroy.sh dev --confirm
```

**Arguments:**
- `environment` (required): Environment name (dev, test)
- `--central-profile`: AWS profile for central account (default: "default")
- `--shared-profiles`: Comma-separated AWS profiles for shared accounts (default: "default")
- `--confirm`: Skip confirmation prompt

**What it does:**
- Destroys infrastructure for each shared account (in reverse order)
- Leaves S3 state bucket and ECR repositories intact (manual cleanup required)

### cleanup.sh
Removes temporary files and caches from the project.

**Usage:**
```bash
./cleanup.sh
```

**What it does:**
- Removes Python cache files (`__pycache__`, `*.pyc`)
- Removes coverage reports
- Removes build artifacts
- Removes IDE temporary files

## Deployment Workflows

### Single Account Deployment

For development/testing in a single AWS account:

```bash
# 1. Setup
./setup.sh dev

# 2. Deploy (plan)
./deploy.sh dev

# 3. Deploy (apply)
./deploy.sh dev --apply

# 4. Destroy (when done)
./destroy.sh dev --confirm
```

### Multi-Account Deployment

For production with separate central and shared accounts:

```bash
# 1. Configure AWS profiles in ~/.aws/credentials
# [central-prod]
# aws_access_key_id = ...
# aws_secret_access_key = ...
#
# [shared-prod]
# aws_access_key_id = ...
# aws_secret_access_key = ...

# 2. Setup
./setup.sh test central-prod shared-prod

# 3. Deploy (plan)
./deploy.sh test --central-profile central-prod --shared-profiles shared-prod

# 4. Deploy (apply)
./deploy.sh test --apply --central-profile central-prod --shared-profiles shared-prod

# 5. Destroy (when done)
./destroy.sh test --central-profile central-prod --shared-profiles shared-prod
```

### Multi-Shared-Account Deployment

For production with one central and multiple shared accounts:

```bash
# 1. Configure AWS profiles
# [central-prod]
# [shared-account-1]
# [shared-account-2]
# [shared-account-3]

# 2. Setup (once)
./setup.sh test central-prod

# 3. Deploy to all shared accounts (comma-separated)
./deploy.sh test --apply \
  --central-profile central-prod \
  --shared-profiles "shared-account-1,shared-account-2,shared-account-3"

# 4. Destroy all
./destroy.sh test \
  --central-profile central-prod \
  --shared-profiles "shared-account-1,shared-account-2,shared-account-3" \
  --confirm
```

**How it works:**
- Central account deployed once (ALB, ECS, VPC endpoints, CloudWatch Logs)
- Each shared account deployed sequentially:
  - Deploys Bedrock guardrails and IAM roles
  - Writes guardrail registry to central account SSM: `/bedrock-gateway/{env}/guardrails/account/{account-id}`
- Guardrail consolidation runs automatically after all shared accounts:
  - Reads all account registry entries from SSM
  - Merges into consolidated config: `/bedrock-gateway/{env}/guardrails/consolidated-config`
- All shared accounts write logs to central account's CloudWatch Log Group

## Environment Variables

- `AWS_REGION`: AWS region for deployment (default: us-east-1)
- `AWS_PROFILE`: Default AWS profile (overridden by --central-profile/--shared-profile)

## Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed (for image builds)
- Terraform 1.12+ (installed by setup.sh if missing)
- UV package manager (installed by setup.sh if missing)
- jq (for JSON parsing in deploy.sh)

## Notes

- The setup script creates S3 buckets with versioning and encryption enabled
- Terraform state is stored in S3 with native file locking (no DynamoDB required)
- Docker images are built only in the central account
- The deploy script uses intelligent change detection to avoid unnecessary image rebuilds
- Backend configuration files are environment-specific (`backend-dev.tfbackend`, `backend-test.tfbackend`)
