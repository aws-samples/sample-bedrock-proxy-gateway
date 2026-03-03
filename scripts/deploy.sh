#!/bin/bash

# GenAI Gateway Deployment Script
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
        --env)
            ENVIRONMENT="$2"
            shift 2
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

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|test)$ ]]; then
    echo "❌ Error: Invalid environment '$ENVIRONMENT'. Must be one of: dev, test"
    exit 1
fi

# Configuration
TFVARS_FILE="${ENVIRONMENT}.tfvars"
LOCAL_TFVARS_FILE="${ENVIRONMENT}.local.tfvars"
BACKEND_FILE="backend-${ENVIRONMENT}.tfbackend"
LOCAL_BACKEND_FILE="backend-${ENVIRONMENT}.local.tfbackend"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
export AWS_REGION=us-east-1

# Set default profiles if not provided
if [ -z "$CENTRAL_PROFILE" ]; then
    CENTRAL_PROFILE="default"
fi
if [ -z "$SHARED_PROFILES" ]; then
    SHARED_PROFILES="default"
fi

# Get central account ID
CENTRAL_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$CENTRAL_PROFILE" --query Account --output text 2>/dev/null)
if [ -z "$CENTRAL_ACCOUNT_ID" ]; then
    echo "❌ Error: Unable to get central account ID. Please configure AWS credentials."
    exit 1
fi

echo "🚀 Starting deployment to $ENVIRONMENT environment"
echo "Central Account: $CENTRAL_ACCOUNT_ID (profile: $CENTRAL_PROFILE)"

# Parse shared profiles and get account IDs
IFS=',' read -ra PROFILE_ARRAY <<< "$SHARED_PROFILES"
SHARED_ACCOUNT_IDS=()
echo "Shared Accounts:"
for profile in "${PROFILE_ARRAY[@]}"; do
    profile=$(echo "$profile" | xargs)  # trim whitespace
    account_id=$(aws sts get-caller-identity --profile "$profile" --query Account --output text 2>/dev/null)
    if [ -z "$account_id" ]; then
        echo "❌ Error: Unable to get account ID for profile: $profile"
        exit 1
    fi
    SHARED_ACCOUNT_IDS+=("$account_id")
    echo "  - $account_id (profile: $profile)"
done

if [ "$APPLY_FLAG" = true ]; then
    echo "🔥 Apply mode enabled - changes will be applied"
else
    echo "📋 Plan mode - only showing planned changes"
fi

# Check if we're in the right directory
if [ ! -d "infrastructure" ]; then
    echo "❌ Error: infrastructure directory not found. Please run this script from the project root."
    exit 1
fi

# Run setup script for environment
echo "🔧 Running setup for $ENVIRONMENT environment..."
cd infrastructure

# Check if tfvars file exists (prefer .local version)
if [ -f "$LOCAL_TFVARS_FILE" ]; then
    TFVARS_FILE="$LOCAL_TFVARS_FILE"
    echo "✓ Using local config: $LOCAL_TFVARS_FILE"
elif [ ! -f "$TFVARS_FILE" ]; then
    echo "❌ Error: Neither $LOCAL_TFVARS_FILE nor $TFVARS_FILE found"
    exit 1
fi

# Check if backend file exists (prefer .local version)
if [ -f "$LOCAL_BACKEND_FILE" ]; then
    BACKEND_FILE="$LOCAL_BACKEND_FILE"
    echo "✓ Using local backend config: $BACKEND_FILE"
elif [ ! -f "$BACKEND_FILE" ]; then
    echo "❌ Error: Neither $LOCAL_BACKEND_FILE nor $BACKEND_FILE found"
    exit 1
fi

echo "🔧 Executing setup.sh..."
if AWS_PROFILE="$CENTRAL_PROFILE" ./setup.sh $ENVIRONMENT central > setup_output.log 2>&1; then
    echo "✅ Setup.sh completed successfully"
else
    echo "❌ Setup.sh failed with exit code $?"
    echo "Error output:"
    cat setup_output.log
    exit 1
fi
echo "script_result ==>"
if [ -f setup_output.log ]; then
    cat setup_output.log
else
    echo "❌ setup_output.log not found"
    exit 1
fi
echo "📊 Extracting IMAGE_TAG..."
IMAGE_TAG=$(tail -n 1 setup_output.log)
echo "IMAGE_TAG ==> $IMAGE_TAG"

# Initialize Terraform
echo "🔧 Initializing Terraform..."
terraform init --reconfigure --backend-config="$BACKEND_FILE"

# Deploy to each shared account
for i in "${!PROFILE_ARRAY[@]}"; do
    SHARED_PROFILE="${PROFILE_ARRAY[$i]}"
    SHARED_PROFILE=$(echo "$SHARED_PROFILE" | xargs)  # trim whitespace
    SHARED_ACCOUNT_ID="${SHARED_ACCOUNT_IDS[$i]}"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📦 Deploying to Shared Account: $SHARED_ACCOUNT_ID (profile: $SHARED_PROFILE)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Plan Account Resources
    echo "📋 Planning deployment..."
    terraform plan --var-file "$TFVARS_FILE" \
        --var="environment=$ENVIRONMENT" \
        --var="aws_region=$AWS_REGION" \
        --var="gw_api_image_tag=$IMAGE_TAG" \
        --var="central_account_profile=$CENTRAL_PROFILE" \
        --var="shared_account_profile=$SHARED_PROFILE" \
        --input=false

    # Apply Account Resources
    if [ "$APPLY_FLAG" = true ]; then
        echo "🚀 Applying deployment..."
        terraform apply --var-file "$TFVARS_FILE" \
            --var="environment=$ENVIRONMENT" \
            --var="aws_region=$AWS_REGION" \
            --var="gw_api_image_tag=$IMAGE_TAG" \
            --var="central_account_profile=$CENTRAL_PROFILE" \
            --var="shared_account_profile=$SHARED_PROFILE" \
            --input=false \
            --auto-approve
        echo "✅ Deployment completed for $SHARED_ACCOUNT_ID!"
    fi
done

if [ "$APPLY_FLAG" = true ]; then
    echo ""
    echo "🔍 Checking consolidated guardrail configuration..."
    SSM_PARAM_NAME="bedrock-gateway/$ENVIRONMENT/guardrails/consolidated-config"

    if aws ssm get-parameter --name "/$SSM_PARAM_NAME" --profile "$CENTRAL_PROFILE" --query 'Parameter.Value' --output text 2>/dev/null >/dev/null; then
        echo "📋 Consolidated Guardrails:"
        aws ssm get-parameter --name "/$SSM_PARAM_NAME" --profile "$CENTRAL_PROFILE" --query 'Parameter.Value' --output text | jq .
    else
        echo "⚠️  Consolidated config not found yet (will be created on next deployment)"
    fi
fi

echo ""
echo "✅ All deployments completed successfully!"
