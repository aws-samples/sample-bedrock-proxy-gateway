#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
set -e

echo "🚀 Setting up Bedrock Proxy Gateway..."

# Detect OS
OS="$(uname -s)"
case "${OS}" in
    Linux*)     PLATFORM=Linux;;
    Darwin*)    PLATFORM=Mac;;
    CYGWIN*|MINGW*|MSYS*) PLATFORM=Windows;;
    *)          PLATFORM="UNKNOWN:${OS}"
esac

echo "📋 Detected platform: $PLATFORM"

# Parse arguments
ENVIRONMENT=${1:-dev}
CENTRAL_PROFILE=${2:-default}

# Resolve project root (scripts/ is one level down from root)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$PROJECT_ROOT/infrastructure"

# Get AWS region
AWS_REGION=${AWS_REGION:-us-east-1}

# Read app_id from tfvars (prefer local, fallback to base)
TFVARS_FILE="$INFRA_DIR/${ENVIRONMENT}.local.tfvars"
if [ ! -f "$TFVARS_FILE" ]; then
    TFVARS_FILE="$INFRA_DIR/${ENVIRONMENT}.tfvars"
fi
if [ ! -f "$TFVARS_FILE" ]; then
    echo "❌ Error: Neither ${ENVIRONMENT}.local.tfvars nor ${ENVIRONMENT}.tfvars found in infrastructure/"
    exit 1
fi
APP_ID=$(grep -E '^\s*app_id\s*=' "$TFVARS_FILE" 2>/dev/null | sed 's/.*=\s*"\(.*\)"/\1/' || echo "myapp")
if [ -z "$APP_ID" ]; then APP_ID="myapp"; fi
echo "📦 Using app_id: $APP_ID (from $(basename $TFVARS_FILE))"

# Get AWS account ID
echo "🔑 Getting AWS account ID..."
ACCOUNT_ID=$(aws sts get-caller-identity --profile "$CENTRAL_PROFILE" --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT_ID" ] || [ "$ACCOUNT_ID" = "None" ]; then
    echo "❌ Error: Unable to get AWS account ID. Check your credentials."
    exit 1
fi
echo "📋 Account: $ACCOUNT_ID (profile: $CENTRAL_PROFILE)"
echo "📋 Region: $AWS_REGION"
echo "📋 Environment: $ENVIRONMENT"

# Resource names
BUCKET_NAME="s3-np-${APP_ID}-${ENVIRONMENT}-${ACCOUNT_ID}-terraform-state"
ECR_REPO_NAME="${APP_ID}-${ENVIRONMENT}-bedrock-proxy-gateway"
OTEL_ECR_REPO_NAME="${APP_ID}-${ENVIRONMENT}-otel-collector"
REGION=$AWS_REGION

# ============================================================================
# Install tools
# ============================================================================
echo "📦 Checking required tools..."

install_uv() {
    if ! command -v uv &> /dev/null; then
        echo "  Installing UV..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "  ✅ UV already installed"
    fi
}

case "${PLATFORM}" in
    Linux)
        install_uv
        if ! command -v terraform &> /dev/null; then
            echo "  Installing Terraform..."
            sudo apt-get update && sudo apt-get install -y gnupg software-properties-common wget
            wget -O- https://apt.releases.hashicorp.com/gpg | \
                gpg --dearmor | \
                sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
                sudo tee /etc/apt/sources.list.d/hashicorp.list
            sudo apt update
            sudo apt-get install -y terraform
        else
            echo "  ✅ Terraform already installed"
        fi
        ;;
    Mac)
        install_uv
        if ! command -v terraform &> /dev/null; then
            if command -v brew &> /dev/null; then
                brew tap hashicorp/tap
                brew install hashicorp/tap/terraform
            else
                echo "  ⚠️  Homebrew not found. Please install Terraform manually from https://www.terraform.io/downloads"
            fi
        else
            echo "  ✅ Terraform already installed"
        fi
        ;;
    Windows)
        install_uv
        if ! command -v terraform &> /dev/null; then
            echo "  ⚠️  Please install Terraform manually from https://www.terraform.io/downloads"
            echo "      Or use Chocolatey: choco install terraform"
        else
            echo "  ✅ Terraform already installed"
        fi
        ;;
    *)
        echo "❌ Unsupported platform: ${PLATFORM}"
        exit 1
        ;;
esac

# Setup Python environment
echo "🐍 Setting up Python environment..."
if command -v uv &> /dev/null; then
    cd "$PROJECT_ROOT" && uv sync --group dev
else
    echo "⚠️  UV not found in PATH. Please restart your shell or add ~/.local/bin to PATH"
fi

# ============================================================================
# S3 bucket for Terraform state
# ============================================================================
echo "🪣 Setting up S3 bucket: $BUCKET_NAME"

if aws s3api head-bucket --bucket "$BUCKET_NAME" --region "$REGION" --profile "$CENTRAL_PROFILE" 2>/dev/null; then
    echo "  ✅ S3 bucket already exists"
else
    echo "  Creating S3 bucket..."
    if [ "$REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION" --profile "$CENTRAL_PROFILE"
    else
        aws s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "$REGION" \
            --create-bucket-configuration LocationConstraint="$REGION" \
            --profile "$CENTRAL_PROFILE"
    fi

    aws s3api put-bucket-encryption \
        --bucket "$BUCKET_NAME" \
        --server-side-encryption-configuration '{
            "Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                }
            }]
        }' \
        --profile "$CENTRAL_PROFILE"

    aws s3api put-public-access-block \
        --bucket "$BUCKET_NAME" \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
        --profile "$CENTRAL_PROFILE"

    aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --region "$REGION" --profile "$CENTRAL_PROFILE" --policy "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [{
        \"Effect\": \"Deny\",
        \"Principal\": \"*\",
        \"Action\": [\"s3:DeleteObject\", \"s3:DeleteBucket\"],
        \"Resource\": [
          \"arn:aws:s3:::$BUCKET_NAME\",
          \"arn:aws:s3:::$BUCKET_NAME/*\"
        ]
      }]
    }"

    echo "  ✅ S3 bucket created and configured"
fi

# ============================================================================
# ECR repositories
# ============================================================================
echo "🐳 Setting up ECR repositories..."

if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --profile "$CENTRAL_PROFILE" --region "$REGION" 2>/dev/null; then
    echo "  ✅ ECR repository $ECR_REPO_NAME already exists"
else
    echo "  Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository \
        --repository-name "$ECR_REPO_NAME" \
        --image-tag-mutability IMMUTABLE \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=KMS \
        --profile "$CENTRAL_PROFILE" \
        --region "$REGION"

    aws ecr put-lifecycle-policy \
        --repository-name "$ECR_REPO_NAME" \
        --profile "$CENTRAL_PROFILE" \
        --region "$REGION" \
        --lifecycle-policy-text '{
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Keep last 10 images",
                    "selection": {
                        "tagStatus": "tagged",
                        "tagPrefixList": ["2"],
                        "countType": "imageCountMoreThan",
                        "countNumber": 10
                    },
                    "action": { "type": "expire" }
                },
                {
                    "rulePriority": 2,
                    "description": "Delete untagged images older than 7 days",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 7
                    },
                    "action": { "type": "expire" }
                }
            ]
        }'
fi

if aws ecr describe-repositories --repository-names "$OTEL_ECR_REPO_NAME" --profile "$CENTRAL_PROFILE" --region "$REGION" 2>/dev/null; then
    echo "  ✅ OTEL ECR repository $OTEL_ECR_REPO_NAME already exists"
else
    echo "  Creating OTEL ECR repository: $OTEL_ECR_REPO_NAME"
    aws ecr create-repository \
        --repository-name "$OTEL_ECR_REPO_NAME" \
        --image-tag-mutability MUTABLE \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=KMS \
        --profile "$CENTRAL_PROFILE" \
        --region "$REGION"

    aws ecr put-lifecycle-policy \
        --repository-name "$OTEL_ECR_REPO_NAME" \
        --profile "$CENTRAL_PROFILE" \
        --region "$REGION" \
        --lifecycle-policy-text '{
            "rules": [
                {
                    "rulePriority": 1,
                    "description": "Delete untagged images older than 1 day",
                    "selection": {
                        "tagStatus": "untagged",
                        "countType": "sinceImagePushed",
                        "countUnit": "days",
                        "countNumber": 1
                    },
                    "action": { "type": "expire" }
                }
            ]
        }'
fi

# ============================================================================
# Build and push Docker images
# ============================================================================
IMAGE_TAG=""
ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
ECR_REPO="$ECR_REGISTRY/$ECR_REPO_NAME"

if [ -d "$PROJECT_ROOT/backend/app" ]; then
    echo "🐳 Building Docker images with change detection..."

    # Login to ECR
    aws ecr get-login-password --region $REGION --profile "$CENTRAL_PROFILE" | docker login --username AWS --password-stdin $ECR_REGISTRY 2>/dev/null

    # --- App image ---
    APP_HASH=$(find "$PROJECT_ROOT/backend/app" -type f -exec sha256sum {} \; | sort -k 2 | sha256sum | cut -d' ' -f1)
    echo "📊 Current app folder hash: $APP_HASH"

    SSM_HASH_PARAM="/bedrock-proxy-gateway/$ENVIRONMENT/app-hash"
    SSM_IMAGE_PARAM="/bedrock-proxy-gateway/$ENVIRONMENT/image-tag"

    STORED_HASH=$(aws ssm get-parameter --name "$SSM_HASH_PARAM" --profile "$CENTRAL_PROFILE" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
    STORED_IMAGE=$(aws ssm get-parameter --name "$SSM_IMAGE_PARAM" --profile "$CENTRAL_PROFILE" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

    IMAGE_EXISTS_IN_ECR=false
    if [ "$APP_HASH" = "$STORED_HASH" ] && [ -n "$STORED_IMAGE" ] && echo "$STORED_IMAGE" | grep -q "$ECR_REPO_NAME"; then
        STORED_TAG=$(echo "$STORED_IMAGE" | sed 's/.*://')
        if aws ecr describe-images --repository-name "$ECR_REPO_NAME" --image-ids imageTag="$STORED_TAG" --region "$REGION" --profile "$CENTRAL_PROFILE" >/dev/null 2>&1; then
            IMAGE_EXISTS_IN_ECR=true
        fi
    fi

    if [ "$IMAGE_EXISTS_IN_ECR" = true ]; then
        echo "  ✅ No changes detected. Using existing image: $STORED_IMAGE"
        IMAGE_TAG="$STORED_IMAGE"
    else
        echo "  🔄 Building new Docker image..."
        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
        IMAGE_TAG="$ECR_REPO:$TIMESTAMP-${APP_HASH:0:8}"

        cd "$PROJECT_ROOT/backend/app"
        docker buildx build --platform linux/amd64 -t $IMAGE_TAG .
        docker push $IMAGE_TAG
        echo "  ✅ Image pushed: $IMAGE_TAG"

        aws ssm put-parameter --name "$SSM_HASH_PARAM" --value "$APP_HASH" --type String --overwrite --profile "$CENTRAL_PROFILE" --region "$REGION"
        aws ssm put-parameter --name "$SSM_IMAGE_PARAM" --value "$IMAGE_TAG" --type String --overwrite --profile "$CENTRAL_PROFILE" --region "$REGION"
    fi

    # --- OTEL collector image ---
    if [ -f "$PROJECT_ROOT/backend/app/OtelDockerfile" ]; then
        OTEL_HASH=$(sha256sum "$PROJECT_ROOT/backend/app/OtelDockerfile" | cut -d' ' -f1)

        SSM_OTEL_HASH_PARAM="/bedrock-proxy-gateway/$ENVIRONMENT/otel-hash"
        SSM_OTEL_IMAGE_PARAM="/bedrock-proxy-gateway/$ENVIRONMENT/otel-image-tag"

        STORED_OTEL_HASH=$(aws ssm get-parameter --name "$SSM_OTEL_HASH_PARAM" --profile "$CENTRAL_PROFILE" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
        STORED_OTEL_IMAGE=$(aws ssm get-parameter --name "$SSM_OTEL_IMAGE_PARAM" --profile "$CENTRAL_PROFILE" --region "$REGION" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

        OTEL_IMAGE_EXISTS_IN_ECR=false
        if [ "$OTEL_HASH" = "$STORED_OTEL_HASH" ] && [ -n "$STORED_OTEL_IMAGE" ] && echo "$STORED_OTEL_IMAGE" | grep -q "$OTEL_ECR_REPO_NAME"; then
            if aws ecr describe-images --repository-name "$OTEL_ECR_REPO_NAME" --image-ids imageTag=latest --region "$REGION" --profile "$CENTRAL_PROFILE" >/dev/null 2>&1; then
                OTEL_IMAGE_EXISTS_IN_ECR=true
            fi
        fi

        if [ "$OTEL_IMAGE_EXISTS_IN_ECR" = true ]; then
            echo "  ✅ No OTEL changes detected. Using existing image."
        else
            echo "  🔄 Building new OTEL collector image..."
            OTEL_IMAGE_TAG="$ECR_REGISTRY/$OTEL_ECR_REPO_NAME:latest"

            cd "$PROJECT_ROOT/backend/app"
            docker buildx build --platform linux/amd64 -f OtelDockerfile -t $OTEL_IMAGE_TAG .
            docker push $OTEL_IMAGE_TAG
            echo "  ✅ OTEL image pushed: $OTEL_IMAGE_TAG"

            aws ssm put-parameter --name "$SSM_OTEL_HASH_PARAM" --value "$OTEL_HASH" --type String --overwrite --profile "$CENTRAL_PROFILE" --region "$REGION"
            aws ssm put-parameter --name "$SSM_OTEL_IMAGE_PARAM" --value "$OTEL_IMAGE_TAG" --type String --overwrite --profile "$CENTRAL_PROFILE" --region "$REGION"
        fi
    fi
else
    echo "⚠️  App directory not found, skipping Docker build"
fi

# ============================================================================
# Backend configuration file
# ============================================================================
BACKEND_FILE="$INFRA_DIR/central-${ENVIRONMENT}.tfbackend"

echo "📝 Creating backend configuration: $BACKEND_FILE"
cat > "$BACKEND_FILE" << EOF
bucket       = "$BUCKET_NAME"
key          = "bedrock-proxy-gateway/${ENVIRONMENT}/terraform.tfstate"
region       = "$REGION"
use_lockfile = true
EOF

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "✅ Setup complete!"
echo "   App ID:       $APP_ID"
echo "   Account:      $ACCOUNT_ID"
echo "   S3 Bucket:    $BUCKET_NAME"
echo "   Backend file: $BACKEND_FILE"
echo "   ECR (app):    $ECR_REPO_NAME"
echo "   ECR (otel):   $OTEL_ECR_REPO_NAME"
if [ -n "$IMAGE_TAG" ]; then
    echo "   Image tag:    $IMAGE_TAG"
fi

echo "$IMAGE_TAG"
