# Deployment Scripts

This directory contains scripts for setting up, deploying, and managing the Bedrock Proxy Gateway infrastructure.

## Scripts Overview

### setup.sh

Sets up the AWS environment for deployment. Installs required tools, creates S3 bucket for Terraform state, ECR repositories, builds and pushes Docker images, and generates backend configuration.

**Usage:**

```bash
# Single account (uses default AWS profile)
./scripts/setup.sh dev

# With custom profile
./scripts/setup.sh dev my-profile
```

**Arguments:**

- `environment` (optional): Environment name (default: dev)
- `profile` (optional): AWS profile for the account (default: "default")

The script reads `app_id` from `{environment}.local.tfvars` (or `{environment}.tfvars` as fallback) to name resources. Default: `myapp`.

**What it does:**

- Detects OS and installs UV and Terraform if missing
- Sets up Python environment with `uv sync`
- Creates S3 bucket for Terraform state (with encryption, public access block)
- Creates ECR repositories for the gateway and OTel collector images
- Builds and pushes Docker images with intelligent change detection (skips rebuild if no changes)
- Generates backend configuration file (`infrastructure/central-{env}.tfbackend`)

**Note:** The deploy script calls setup.sh automatically. You can run it independently for debugging or inspecting resource state.

### deploy.sh

Deploys the infrastructure using Terraform.

**Usage:**

```bash
# Plan only (default)
./scripts/deploy.sh dev

# Plan with custom profiles (single shared account)
./scripts/deploy.sh dev --central-profile central --shared-profiles shared

# Plan with multiple shared accounts
./scripts/deploy.sh dev --central-profile central --shared-profiles "shared-1,shared-2,shared-3"

# Apply changes
./scripts/deploy.sh dev --apply

# Apply with multiple shared accounts
./scripts/deploy.sh dev --apply \
  --central-profile central \
  --shared-profiles "shared-1,shared-2,shared-3"
```

**Arguments:**

- `environment` (required): Environment name (dev, test)
- `--apply`: Apply changes (default is plan only)
- `--central-profile`: AWS profile for central account (default: "default")
- `--shared-profiles`: Comma-separated AWS profiles for shared accounts (default: "default")

**What it does:**

- Runs infrastructure setup script (builds/pushes Docker images with change detection)
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
./scripts/destroy.sh dev

# With custom profiles (single shared account)
./scripts/destroy.sh dev --central-profile central --shared-profiles shared

# With multiple shared accounts
./scripts/destroy.sh dev \
  --central-profile central \
  --shared-profiles "shared-1,shared-2,shared-3"

# Skip confirmation prompt
./scripts/destroy.sh dev --confirm
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
./scripts/cleanup.sh
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
# 1. Configure
cd infrastructure
cp dev.tfvars dev.local.tfvars
# Edit dev.local.tfvars with your app_id, OAuth provider, and AWS account details

# 2. Deploy (plan)
cd ..
./scripts/deploy.sh dev

# 3. Deploy (apply)
./scripts/deploy.sh dev --apply

# 4. Destroy (when done)
./scripts/destroy.sh dev --confirm
```

### Multi-Account Deployment

For deployments with separate central and shared accounts:

```bash
# 1. Configure AWS profiles in ~/.aws/credentials
# [central]
# aws_access_key_id = ...
# aws_secret_access_key = ...
#
# [shared]
# aws_access_key_id = ...
# aws_secret_access_key = ...

# 2. Configure
cd infrastructure
cp dev.tfvars dev.local.tfvars
# Edit dev.local.tfvars with your app_id, OAuth provider, and AWS account details

# 3. Deploy (plan)
cd ..
./scripts/deploy.sh dev --central-profile central --shared-profiles shared

# 4. Deploy (apply)
./scripts/deploy.sh dev --apply --central-profile central --shared-profiles shared

# 5. Destroy (when done)
./scripts/destroy.sh dev --central-profile central --shared-profiles shared
```

### Multi-Shared-Account Deployment

For deployments with one central and multiple shared accounts:

```bash
# 1. Configure AWS profiles
# [central]
# [shared-account-1]
# [shared-account-2]
# [shared-account-3]

# 2. Configure
cd infrastructure
cp test.tfvars test.local.tfvars
# Edit test.local.tfvars with your app_id, OAuth provider, and AWS account details

# 3. Deploy to all shared accounts (comma-separated)
cd ..
./scripts/deploy.sh test --apply \
  --central-profile central \
  --shared-profiles "shared-account-1,shared-account-2,shared-account-3"

# 4. Destroy all
./scripts/destroy.sh test \
  --central-profile central \
  --shared-profiles "shared-account-1,shared-account-2,shared-account-3" \
  --confirm
```

**How it works:**

- Central account deployed once (ALB, ECS, VPC endpoints, CloudWatch Logs)
- Each shared account deployed sequentially:
  - Deploys Bedrock guardrails and IAM roles
  - Writes guardrail registry to central account SSM: `/bedrock-proxy-gateway/{env}/guardrails/account/{account-id}`
- Guardrail consolidation runs automatically after all shared accounts:
  - Reads all account registry entries from SSM
  - Merges into consolidated config: `/bedrock-proxy-gateway/{env}/guardrails/consolidated-config`
- All shared accounts write logs to central account's CloudWatch Log Group

## Environment Variables

- `AWS_REGION`: AWS region for deployment (default: us-east-1)
- `AWS_PROFILE`: Default AWS profile (overridden by --central-profile/--shared-profiles)

## Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed (for image builds)
- Terraform 1.5+
- jq (for JSON parsing in deploy.sh)

## Notes

- The setup script creates S3 buckets with encryption enabled
- Terraform state is stored in S3 with native file locking (no DynamoDB required)
- Docker images are built only in the central account
- The deploy script uses intelligent change detection to avoid unnecessary image rebuilds
- Backend configuration files are environment-specific (`central-dev.tfbackend`, `central-test.tfbackend`)
- All scripts are idempotent — safe to run multiple times
