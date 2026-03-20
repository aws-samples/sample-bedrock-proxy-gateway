#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# GenAI Gateway Destroy Script - reverse 3-stage: consolidation → shared×N → central
set -e

ENVIRONMENT="dev"
CENTRAL_PROFILE=""
SHARED_PROFILES=""
CONFIRM=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --confirm) CONFIRM=true; shift ;;
        --central-profile) CENTRAL_PROFILE="$2"; shift 2 ;;
        --shared-profiles) SHARED_PROFILES="$2"; shift 2 ;;
        *) ENVIRONMENT="$1"; shift ;;
    esac
done

if [[ ! "$ENVIRONMENT" =~ ^(dev|test)$ ]]; then
    echo "❌ Error: Invalid environment '$ENVIRONMENT'. Must be: dev, test"
    exit 1
fi

CENTRAL_PROFILE="${CENTRAL_PROFILE:-default}"
SHARED_PROFILES="${SHARED_PROFILES:-default}"
export AWS_REGION=us-east-1

# Resolve accounts
CENTRAL_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$CENTRAL_PROFILE" --query Account --output text 2>/dev/null)
if [ -z "$CENTRAL_ACCOUNT_ID" ]; then
    echo "❌ Error: Unable to get central account ID."
    exit 1
fi

echo "🔥 Destroying $ENVIRONMENT environment"
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

if [ "$CONFIRM" != true ]; then
    echo ""
    echo "⚠️  This will DESTROY all infrastructure. Type 'yes' to confirm:"
    read -r response
    if [ "$response" != "yes" ]; then
        echo "Aborted."
        exit 0
    fi
fi

if [ ! -d "infrastructure" ]; then
    echo "❌ Error: infrastructure directory not found. Run from project root."
    exit 1
fi

cd infrastructure

TFVARS_FILE="${ENVIRONMENT}.local.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then TFVARS_FILE="${ENVIRONMENT}.tfvars"; fi
if [ ! -f "$TFVARS_FILE" ]; then
    echo "❌ Error: No tfvars file found for $ENVIRONMENT"
    exit 1
fi
TFVARS_FILE="$(cd "$(dirname "$TFVARS_FILE")" && pwd)/$(basename "$TFVARS_FILE")"

resolve_backend() {
    local stage=$1
    local f="${stage}-${ENVIRONMENT}.local.tfbackend"
    if [ ! -f "$f" ]; then f="${stage}-${ENVIRONMENT}.tfbackend"; fi
    if [ ! -f "$f" ]; then echo "❌ No backend config for '$stage'"; exit 1; fi
    echo "$f"
}

# ============================================================================
# STAGE 1: Destroy Consolidation
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔥 Stage 1: Destroying Guardrail Consolidation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CONSOLIDATION_BACKEND=$(resolve_backend "consolidation")
terraform -chdir=consolidation init --reconfigure --backend-config="../$CONSOLIDATION_BACKEND"
terraform -chdir=consolidation destroy --var-file "$TFVARS_FILE" \
    --var="central_account_profile=$CENTRAL_PROFILE" \
    --auto-approve
echo "✅ Consolidation destroyed"

# ============================================================================
# STAGE 2: Destroy Shared Accounts (reverse order)
# ============================================================================
SHARED_BACKEND=$(resolve_backend "shared")
terraform -chdir=shared init --reconfigure --backend-config="../$SHARED_BACKEND"

for ((i=${#PROFILE_ARRAY[@]}-1; i>=0; i--)); do
    SHARED_PROFILE=$(echo "${PROFILE_ARRAY[$i]}" | xargs)
    SHARED_ACCOUNT_ID="${SHARED_ACCOUNT_IDS[$i]}"
    WORKSPACE="shared-${SHARED_ACCOUNT_ID}"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🔥 Stage 2: Destroying Shared Account $SHARED_ACCOUNT_ID (profile: $SHARED_PROFILE)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    terraform -chdir=shared workspace select "$WORKSPACE" 2>/dev/null || { echo "⚠️  Workspace $WORKSPACE not found, skipping"; continue; }

    terraform -chdir=shared destroy --var-file "$TFVARS_FILE" \
        --var="central_account_profile=$CENTRAL_PROFILE" \
        --var="shared_account_profile=$SHARED_PROFILE" \
        --auto-approve

    terraform -chdir=shared workspace select default
    terraform -chdir=shared workspace delete "$WORKSPACE"
    echo "✅ Shared account $SHARED_ACCOUNT_ID destroyed"
done

# ============================================================================
# STAGE 3: Destroy Central Account
# ============================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔥 Stage 3: Destroying Central Account ($CENTRAL_ACCOUNT_ID)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CENTRAL_BACKEND=$(resolve_backend "central")
terraform -chdir=central init --reconfigure --backend-config="../$CENTRAL_BACKEND"
terraform -chdir=central destroy --var-file "$TFVARS_FILE" \
    --var="gw_api_image_tag=dummy" \
    --var="central_account_profile=$CENTRAL_PROFILE" \
    --auto-approve
echo "✅ Central account destroyed"

echo ""
echo "✅ All infrastructure destroyed!"
echo ""
echo "💡 Not deleted (manual cleanup if needed):"
echo "   - S3 state bucket"
echo "   - ECR repositories"
