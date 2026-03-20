#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# GenAI Gateway Deployment Script - 3-stage: central → shared×N → consolidation
set -e

# Parse command line arguments
APPLY_FLAG=false
ENVIRONMENT="dev"
CENTRAL_PROFILE=""
SHARED_PROFILES=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --apply)
            APPLY_FLAG=true
            shift
            ;;
        --central-profile)
            CENTRAL_PROFILE="$2"
            shift 2
            ;;
        --shared-profiles)
            SHARED_PROFILES="$2"
            shift 2
            ;;
        *)
            ENVIRONMENT="$1"
            shift
            ;;
    esac
done

if [[ ! "$ENVIRONMENT" =~ ^(dev|test)$ ]]; then
    echo "❌ Error: Invalid environment '$ENVIRONMENT'. Must be: dev, test"
    exit 1
fi

# Defaults
CENTRAL_PROFILE="${CENTRAL_PROFILE:-default}"
SHARED_PROFILES="${SHARED_PROFILES:-default}"
export AWS_REGION=us-east-1

# Resolve accounts
CENTRAL_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$CENTRAL_PROFILE" --query Account --output text 2>/dev/null)
if [ -z "$CENTRAL_ACCOUNT_ID" ]; then
    echo "❌ Error: Unable to get central account ID."
    exit 1
fi

echo "🚀 Starting deployment to $ENVIRONMENT environment"
echo "Central Account: $CENTRAL_ACCOUNT_ID (profile: $CENTRAL_PROFILE)"

IFS=',' read -ra PROFILE_ARRAY <<< "$SHARED_PROFILES"
SHARED_ACCOUNT_IDS=()
echo "Shared Accounts:"
for profile in "${PROFILE_ARRAY[@]}"; do
    profile=$(echo "$profile" | xargs)
    account_id=$(aws sts get-caller-identity --profile "$profile" --query Account --output text 2>/dev/null)
    if [ -z "$account_id" ]; then
        echo "❌ Error: Unable to get account ID for profile: $profile"
        exit 1
    fi
    SHARED_ACCOUNT_IDS+=("$account_id")
    echo "  - $account_id (profile: $profile)"
done

if [ "$APPLY_FLAG" = true ]; then
    echo "🔥 Apply mode enabled"
else
    echo "📋 Plan mode only"
fi

if [ ! -d "infrastructure" ]; then
    echo "❌ Error: infrastructure directory not found. Run from project root."
    exit 1
fi

cd infrastructure

# Resolve tfvars (shared across all stages)
TFVARS_FILE="${ENVIRONMENT}.local.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
    TFVARS_FILE="${ENVIRONMENT}.tfvars"
fi
if [ ! -f "$TFVARS_FILE" ]; then
    echo "❌ Error: No tfvars file found for $ENVIRONMENT"
    exit 1
fi
echo "✓ Using config: $TFVARS_FILE"
# Convert to absolute path for use in subdirectories
TFVARS_FILE="$(cd "$(dirname "$TFVARS_FILE")" && pwd)/$(basename "$TFVARS_FILE")"

# Run setup (S3, ECR, Docker images, backend configs)
echo "🔧 Executing setup.sh..."
if AWS_PROFILE="$CENTRAL_PROFILE" ../scripts/setup.sh "$ENVIRONMENT" "$CENTRAL_PROFILE" > setup_output.log 2>&1; then
    echo "✅ Setup completed"
else
    echo "❌ Setup failed:"
    cat setup_output.log
    exit 1
fi
IMAGE_TAG=$(tail -n 1 setup_output.log)
echo "IMAGE_TAG ==> $IMAGE_TAG"

# Helper: resolve backend file for a stage
resolve_backend() {
    local stage=$1
    local f="${stage}-${ENVIRONMENT}.local.tfbackend"
    if [ ! -f "$f" ]; then f="${stage}-${ENVIRONMENT}.tfbackend"; fi
    if [ ! -f "$f" ]; then
        echo "❌ Error: No backend config found for stage '$stage'"
        exit 1
    fi
    echo "$f"
}

# Helper: plan/apply
tf_deploy() {
    local dir=$1
    shift
    echo "📋 Planning..."
    terraform -chdir="$dir" plan --var-file "$TFVARS_FILE" "$@" --input=false

    if [ "$APPLY_FLAG" = true ]; then
        echo "🚀 Applying..."
        terraform -chdir="$dir" apply --var-file "$TFVARS_FILE" "$@" --input=false --auto-approve
    fi
}

# ============================================================================
# STAGE 1: Central Account
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Stage 1: Central Account ($CENTRAL_ACCOUNT_ID)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CENTRAL_BACKEND=$(resolve_backend "central")
terraform -chdir=central init --reconfigure --backend-config="../$CENTRAL_BACKEND"

tf_deploy central \
    --var="gw_api_image_tag=$IMAGE_TAG" \
    --var="central_account_profile=$CENTRAL_PROFILE"

if [ "$APPLY_FLAG" = true ]; then
    echo "✅ Central account deployed"
fi

# ============================================================================
# STAGE 2: Shared Accounts (one workspace per account)
# ============================================================================
SHARED_BACKEND=$(resolve_backend "shared")
terraform -chdir=shared init --reconfigure --backend-config="../$SHARED_BACKEND"

for i in "${!PROFILE_ARRAY[@]}"; do
    SHARED_PROFILE=$(echo "${PROFILE_ARRAY[$i]}" | xargs)
    SHARED_ACCOUNT_ID="${SHARED_ACCOUNT_IDS[$i]}"
    WORKSPACE="shared-${SHARED_ACCOUNT_ID}"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Stage 2: Shared Account $SHARED_ACCOUNT_ID (profile: $SHARED_PROFILE)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    terraform -chdir=shared workspace select "$WORKSPACE" 2>/dev/null || \
        terraform -chdir=shared workspace new "$WORKSPACE"

    tf_deploy shared \
        --var="central_account_profile=$CENTRAL_PROFILE" \
        --var="shared_account_profile=$SHARED_PROFILE"

    if [ "$APPLY_FLAG" = true ]; then
        echo "✅ Shared account $SHARED_ACCOUNT_ID deployed"
    fi
done

# ============================================================================
# STAGE 3: Guardrail Consolidation
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📦 Stage 3: Guardrail Consolidation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CONSOLIDATION_BACKEND=$(resolve_backend "consolidation")
terraform -chdir=consolidation init --reconfigure --backend-config="../$CONSOLIDATION_BACKEND"

tf_deploy consolidation \
    --var="central_account_profile=$CENTRAL_PROFILE"

if [ "$APPLY_FLAG" = true ]; then
    echo "✅ Guardrail consolidation complete"

    echo ""
    echo "🔍 Consolidated guardrail configuration:"
    SSM_PARAM="bedrock-proxy-gateway/$ENVIRONMENT/guardrails/consolidated-config"
    aws ssm get-parameter --name "/$SSM_PARAM" --profile "$CENTRAL_PROFILE" \
        --query 'Parameter.Value' --output text 2>/dev/null | jq . || \
        echo "⚠️  Consolidated config not found yet"
fi

echo ""
echo "✅ All stages completed successfully!"
