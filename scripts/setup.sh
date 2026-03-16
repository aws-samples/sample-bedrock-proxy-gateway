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
SHARED_PROFILE=${3:-default}

# Get AWS account IDs and region
AWS_REGION=${AWS_REGION:-us-east-1}
CENTRAL_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$CENTRAL_PROFILE" --query Account --output text)
SHARED_ACCOUNT_ID=$(aws sts get-caller-identity --profile "$SHARED_PROFILE" --query Account --output text)

echo "📋 Central Account: $CENTRAL_ACCOUNT_ID (profile: $CENTRAL_PROFILE)"
echo "📋 Shared Account: $SHARED_ACCOUNT_ID (profile: $SHARED_PROFILE)"
echo "📋 Region: $AWS_REGION"
echo "📋 Environment: $ENVIRONMENT"

# Create S3 bucket for Terraform state in central account
BUCKET_NAME="bedrock-proxy-gateway-terraform-state-${CENTRAL_ACCOUNT_ID}-${AWS_REGION}"
echo "🪣 Creating S3 bucket for Terraform state: $BUCKET_NAME"

if aws s3 ls "s3://${BUCKET_NAME}" --profile "$CENTRAL_PROFILE" 2>/dev/null; then
    echo "✅ S3 bucket already exists"
else
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$AWS_REGION" --profile "$CENTRAL_PROFILE"
    else
        aws s3api create-bucket \
            --bucket "$BUCKET_NAME" \
            --region "$AWS_REGION" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION" \
            --profile "$CENTRAL_PROFILE"
    fi

    aws s3api put-bucket-versioning \
        --bucket "$BUCKET_NAME" \
        --versioning-configuration Status=Enabled \
        --profile "$CENTRAL_PROFILE"

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

    echo "✅ S3 bucket created and configured"
fi

# Create backend configuration file
BACKEND_DIR="infrastructure"
BACKEND_FILE="$BACKEND_DIR/backend-${ENVIRONMENT}.local.tfbackend"
echo "📝 Creating backend configuration: $BACKEND_FILE"

cat > "$BACKEND_FILE" <<EOF
bucket         = "$BUCKET_NAME"
key            = "bedrock-gateway/${ENVIRONMENT}/terraform.tfstate"
region         = "$AWS_REGION"
use_lockfile   = true
EOF

echo "✅ Backend configuration created"

# Install tools based on platform
echo "📦 Installing required tools..."

case "${PLATFORM}" in
    Linux)
        echo "📦 Installing for Linux..."

        # Install UV
        if ! command -v uv &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi

        # Install Terraform
        if ! command -v terraform &> /dev/null; then
            sudo apt-get update && sudo apt-get install -y gnupg software-properties-common wget
            wget -O- https://apt.releases.hashicorp.com/gpg | \
                gpg --dearmor | \
                sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
                sudo tee /etc/apt/sources.list.d/hashicorp.list
            sudo apt update
            sudo apt-get install -y terraform
        fi
        ;;

    Mac)
        echo "📦 Installing for macOS..."

        # Install UV
        if ! command -v uv &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi

        # Install Terraform via Homebrew
        if ! command -v terraform &> /dev/null; then
            if command -v brew &> /dev/null; then
                brew tap hashicorp/tap
                brew install hashicorp/tap/terraform
            else
                echo "⚠️  Homebrew not found. Please install Terraform manually from https://www.terraform.io/downloads"
            fi
        fi
        ;;

    Windows)
        echo "📦 Installing for Windows..."

        # Install UV
        if ! command -v uv &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="$HOME/.local/bin:$PATH"
        fi

        # Check for Terraform
        if ! command -v terraform &> /dev/null; then
            echo "⚠️  Please install Terraform manually from https://www.terraform.io/downloads"
            echo "    Or use Chocolatey: choco install terraform"
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
    uv sync --group dev
else
    echo "⚠️  UV not found in PATH. Please restart your shell or add ~/.local/bin to PATH"
fi

echo "✅ Setup complete!"
echo ""
echo "📋 Terraform backend configuration:"
echo "   Bucket: $BUCKET_NAME"
echo "   Backend file: $BACKEND_FILE"
echo "   Central Profile: $CENTRAL_PROFILE"
echo "   Shared Profile: $SHARED_PROFILE"
echo ""
echo "💡 Usage:"
echo "   Single account: ./setup.sh dev"
echo "   Multi-account:  ./setup.sh dev central-profile shared-profile"
