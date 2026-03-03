#!/bin/bash

# GenAI Gateway Destroy Script
set -e

# Parse command line arguments
ENVIRONMENT="dev"
CENTRAL_PROFILE=""
SHARED_PROFILES=""
CONFIRM=false

while [[ $# -gt 0 ]]; do
    case $1 in
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
        --confirm)
            CONFIRM=true
            shift
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
BACKEND_FILE="backend-${ENVIRONMENT}.tfbackend"
LOCAL_BACKEND_FILE="backend-${ENVIRONMENT}.local.tfbackend"

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
    echo "❌ Error: Unable to get central account ID."
    exit 1
fi

# Parse shared profiles and get account IDs
IFS=',' read -ra PROFILE_ARRAY <<< "$SHARED_PROFILES"
SHARED_ACCOUNT_IDS=()
for profile in "${PROFILE_ARRAY[@]}"; do
    profile=$(echo "$profile" | xargs)
    account_id=$(aws sts get-caller-identity --profile "$profile" --query Account --output text 2>/dev/null)
    if [ -z "$account_id" ]; then
        echo "❌ Error: Unable to get account ID for profile: $profile"
        exit 1
    fi
    SHARED_ACCOUNT_IDS+=("$account_id")
done

echo "🔥 Destroying infrastructure for $ENVIRONMENT environment"
echo "Central Account: $CENTRAL_ACCOUNT_ID (profile: $CENTRAL_PROFILE)"
echo "Shared Accounts:"
for i in "${!PROFILE_ARRAY[@]}"; do
    echo "  - ${SHARED_ACCOUNT_IDS[$i]} (profile: ${PROFILE_ARRAY[$i]})"
done

# Confirmation prompt
if [ "$CONFIRM" = false ]; then
    echo ""
    echo "⚠️  WARNING: This will destroy all infrastructure in the $ENVIRONMENT environment!"
    echo ""
    read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirmation
    if [ "$confirmation" != "yes" ]; then
        echo "❌ Destroy cancelled"
        exit 0
    fi
fi

# Check if we're in the right directory
if [ ! -d "infrastructure" ]; then
    echo "❌ Error: infrastructure directory not found. Please run this script from the project root."
    exit 1
fi

cd infrastructure

if [ ! -f "$TFVARS_FILE" ]; then
    echo "❌ Error: $TFVARS_FILE not found"
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

# Initialize Terraform
echo "🔧 Initializing Terraform..."
terraform init --reconfigure --backend-config="$BACKEND_FILE"

# Destroy for each shared account (in reverse order)
for ((i=${#PROFILE_ARRAY[@]}-1; i>=0; i--)); do
    SHARED_PROFILE="${PROFILE_ARRAY[$i]}"
    SHARED_PROFILE=$(echo "$SHARED_PROFILE" | xargs)
    SHARED_ACCOUNT_ID="${SHARED_ACCOUNT_IDS[$i]}"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔥 Destroying Shared Account: $SHARED_ACCOUNT_ID (profile: $SHARED_PROFILE)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    terraform destroy --var-file "$TFVARS_FILE" \
        --var="environment=$ENVIRONMENT" \
        --var="aws_region=$AWS_REGION" \
        --var="gw_api_image_tag=dummy" \
        --var="central_account_profile=$CENTRAL_PROFILE" \
        --var="shared_account_profile=$SHARED_PROFILE" \
        --auto-approve

    echo "✅ Destroyed $SHARED_ACCOUNT_ID"
done

echo ""
echo "✅ All infrastructure destroyed successfully!"
echo ""
echo "💡 Note: The following resources were NOT deleted and must be removed manually if needed:"
echo "   - S3 bucket: bedrock-proxy-gateway-terraform-state-${CENTRAL_ACCOUNT_ID}-${AWS_REGION}"
echo "   - ECR repositories in central account"
echo "   - CloudWatch Log Groups (if retention is set)"
