#!/bin/bash
echo "Setup.sh triggered"
set -e

# Check if environment and account type are provided
if [ $# -ne 2 ]; then
    echo "Usage: $0 <environment> <account_type>"
    echo "Example: $0 dev central"
    echo "Example: $0 dev shared"
    exit 1
fi

ENV=$1
ACCOUNT_TYPE=$2

# Get account ID with retry until non-empty
echo "Getting AWS account ID..."
LOOP_COUNT=0
while true; do
    echo "into the Getting AWS account id loop (attempt $((++LOOP_COUNT)))"
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>&1 | grep -v '^$' | head -1)
    echo "ACCOUNT_ID ==> '${ACCOUNT_ID}'"
    if [ -n "$ACCOUNT_ID" ] && [ "$ACCOUNT_ID" != "None" ] && [ "$ACCOUNT_ID" != "null" ]; then
        echo "Valid account ID found: $ACCOUNT_ID"
        break
    fi
    if [ $LOOP_COUNT -gt 10 ]; then
        echo "Failed to get AWS account ID after 10 attempts"
        exit 1
    fi
    echo "Waiting for AWS credentials to be available..."
    sleep 2
done
BUCKET_NAME="s3-np-myapp-${ENV}-${ACCOUNT_ID}-terraform-state"
ECR_REPO_NAME="myapp-${ENV}-bedrock-gateway"
OTEL_ECR_REPO_NAME="myapp-${ENV}-otel-collector"
REGION=${AWS_REGION:-us-east-1}

echo "Setting up Terraform backend for environment: $ENV, account type: $ACCOUNT_TYPE, account: $ACCOUNT_ID"

# Check if S3 bucket exists
if aws s3api head-bucket --bucket "$BUCKET_NAME" --region "$REGION" 2>/dev/null; then
    echo "S3 bucket $BUCKET_NAME already exists"
else
    echo "Creating S3 bucket: $BUCKET_NAME"
    aws s3api create-bucket --bucket "$BUCKET_NAME" --region "$REGION" --acl private

    echo "Enabling versioning for $BUCKET_NAME"
    aws s3api put-bucket-versioning --bucket "$BUCKET_NAME" --region "$REGION" --versioning-configuration Status=Enabled

    echo "Setting bucket policy for $BUCKET_NAME"
    aws s3api put-bucket-policy --bucket "$BUCKET_NAME" --region "$REGION" --policy "{
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
fi

IMAGE_TAG=""
# Create ECR repository and build image only for central account
if [ "$ACCOUNT_TYPE" = "central" ]; then
    # Create ECR repository if it doesn't exist
    if aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" 2>/dev/null; then
        echo "ECR repository $ECR_REPO_NAME already exists"
    else
        echo "Creating ECR repository: $ECR_REPO_NAME"
        aws ecr create-repository \
            --repository-name "$ECR_REPO_NAME" \
            --image-tag-mutability IMMUTABLE \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=KMS

        echo "Setting lifecycle policy for $ECR_REPO_NAME"
        aws ecr put-lifecycle-policy \
            --repository-name "$ECR_REPO_NAME" \
            --lifecycle-policy-text '{
                "rules": [
                    {
                        "rulePriority": 1,
                        "description": "Keep last 10 images",
                        "selection": {
                            "tagStatus": "tagged",
                            "tagPrefixList": ["v"],
                            "countType": "imageCountMoreThan",
                            "countNumber": 10
                        },
                        "action": {
                            "type": "expire"
                        }
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
                        "action": {
                            "type": "expire"
                        }
                    }
                ]
            }'
    fi

    # Create OTEL ECR repository if it doesn't exist
    if aws ecr describe-repositories --repository-names "$OTEL_ECR_REPO_NAME" 2>/dev/null; then
        echo "OTEL ECR repository $OTEL_ECR_REPO_NAME already exists"
    else
        echo "Creating OTEL ECR repository: $OTEL_ECR_REPO_NAME"
        aws ecr create-repository \
            --repository-name "$OTEL_ECR_REPO_NAME" \
            --image-tag-mutability IMMUTABLE \
            --image-scanning-configuration scanOnPush=true \
            --encryption-configuration encryptionType=KMS
    fi

    # Build and push Docker image if app directory exists
    if [ -d "../backend/app" ]; then
        echo "🐳 Building Docker image with intelligent change detection..."

        # Calculate hash of app folder
        APP_HASH=$(find ../backend/app -type f -exec sha256sum {} \; | sort -k 2 | sha256sum | cut -d' ' -f1)
        echo "📊 Current app folder hash: $APP_HASH"

        # SSM parameter names
        SSM_HASH_PARAM="/bedrock-gateway/$ENV/app-hash"
        SSM_IMAGE_PARAM="/bedrock-gateway/$ENV/image-tag"

        # Get stored hash and image tag from SSM
        STORED_HASH=$(aws ssm get-parameter --name "$SSM_HASH_PARAM" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
        STORED_IMAGE=$(aws ssm get-parameter --name "$SSM_IMAGE_PARAM" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

        echo "📋 Stored hash: $STORED_HASH"
        echo "📋 Stored image: $STORED_IMAGE"

        REGION=$(aws configure get region || echo "us-east-1")
        ECR_REGISTRY="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
        # Login to ECR (suppress credential storage warning)
        aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_REGISTRY 2>/dev/null

        # Check if rebuild is needed
        if [ "$APP_HASH" = "$STORED_HASH" ] && [ -n "$STORED_IMAGE" ]; then
            echo "✅ No changes detected in app folder. Using existing image: $STORED_IMAGE"
            IMAGE_TAG="$STORED_IMAGE"
        else
            echo "🔄 Changes detected or first build. Building new Docker image..."

            # Generate new image tag
            TIMESTAMP=$(date +%Y%m%d-%H%M%S)

            ECR_REPO="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPO_NAME"

            IMAGE_TAG="$ECR_REPO:$TIMESTAMP-${APP_HASH:0:8}"
            LATEST_TAG="$ECR_REPO:latest"

            # Build and push image
            cd ../backend/app
            docker buildx build --platform linux/amd64 -t $IMAGE_TAG .
            docker tag $IMAGE_TAG $LATEST_TAG
            docker push $IMAGE_TAG

            echo "✅ Image built and pushed: $IMAGE_TAG"
            cd ../../infrastructure

            # Update SSM parameters
            aws ssm put-parameter --name "$SSM_HASH_PARAM" --value "$APP_HASH" --type String --overwrite
            aws ssm put-parameter --name "$SSM_IMAGE_PARAM" --value "$IMAGE_TAG" --type String --overwrite

            echo "📝 Updated SSM parameters with new hash and image tag"
        fi

        # Build OTEL collector image with change detection
        if [ -f "../backend/app/OtelDockerfile" ]; then
            echo "🔧 Building OTEL collector image with change detection..."

            # Calculate hash of OtelDockerfile
            OTEL_HASH=$(sha256sum ../backend/app/OtelDockerfile | cut -d' ' -f1)
            echo "📊 Current OTEL Dockerfile hash: $OTEL_HASH"

            # SSM parameter names for OTEL
            SSM_OTEL_HASH_PARAM="/bedrock-gateway/$ENV/otel-hash"
            SSM_OTEL_IMAGE_PARAM="/bedrock-gateway/$ENV/otel-image-tag"

            # Get stored OTEL hash and image tag from SSM
            STORED_OTEL_HASH=$(aws ssm get-parameter --name "$SSM_OTEL_HASH_PARAM" --query 'Parameter.Value' --output text 2>/dev/null || echo "")
            STORED_OTEL_IMAGE=$(aws ssm get-parameter --name "$SSM_OTEL_IMAGE_PARAM" --query 'Parameter.Value' --output text 2>/dev/null || echo "")

            echo "📋 Stored OTEL hash: $STORED_OTEL_HASH"
            echo "📋 Stored OTEL image: $STORED_OTEL_IMAGE"

            # Check if OTEL rebuild is needed
            if [ "$OTEL_HASH" = "$STORED_OTEL_HASH" ] && [ -n "$STORED_OTEL_IMAGE" ]; then
                echo "✅ No changes detected in OtelDockerfile. Using existing image: $STORED_OTEL_IMAGE"
            else
                echo "🔄 Changes detected in OtelDockerfile or first build. Building new OTEL image..."
                OTEL_IMAGE_TAG="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$OTEL_ECR_REPO_NAME:latest"

                # Delete existing latest tag if it exists
                echo "🗑️ Attempting to delete existing latest tag..."
                aws ecr batch-delete-image --repository-name "$OTEL_ECR_REPO_NAME" --image-ids imageTag=latest 2>/dev/null || echo "No existing latest tag found"

                cd ../backend/app
                docker buildx build --platform linux/amd64 -f OtelDockerfile -t $OTEL_IMAGE_TAG .
                docker push $OTEL_IMAGE_TAG
                echo "✅ OTEL image built and pushed: $OTEL_IMAGE_TAG"
                cd ../../infrastructure

                # Update OTEL SSM parameters
                aws ssm put-parameter --name "$SSM_OTEL_HASH_PARAM" --value "$OTEL_HASH" --type String --overwrite
                aws ssm put-parameter --name "$SSM_OTEL_IMAGE_PARAM" --value "$OTEL_IMAGE_TAG" --type String --overwrite

                echo "📝 Updated OTEL SSM parameters with new hash and image tag"
            fi
        fi
    else
        echo "⚠️  App directory not found, skipping Docker build"
    fi
else
    echo "Skipping ECR and Docker operations for shared account"
fi

# Create backend configuration file
if [[ "$ENV" == "dev" || "$ENV" == "qa" || "$ENV" == "preprod" || "$ENV" == "prod" ]]; then
    BACKEND_FILE="backend/${ACCOUNT_TYPE}-${ENV}.tfbackend"
else
    BACKEND_FILE="backend/${ENV}.tfbackend"
fi
mkdir -p backend

echo "Creating/Overwriting backend configuration file: $BACKEND_FILE"
cat > "$BACKEND_FILE" << EOF
bucket       = "$BUCKET_NAME"
key          = "terraform.tfstate"
region       = "$REGION"
use_lockfile = true
EOF

echo "Terraform backend setup completed for $ENV environment ($ACCOUNT_TYPE account)"
echo "Backend configuration saved to: $BACKEND_FILE"

echo "$IMAGE_TAG"
