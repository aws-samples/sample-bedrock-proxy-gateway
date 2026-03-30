#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Prerequisites:
# 1. Create .env.dev (or .env.test) at the repository root with:
#    AWS_PROFILE, AWS_REGION, GATEWAY_API_URL, GATEWAY_SECRET_ID
#
# 2. The GATEWAY_SECRET_ID must reference a Secrets Manager secret containing:
#    client_id, client_secret, token_url, audience
#
# 3. Optional: PKCS#12 keystore for mTLS:
#    cd test/integration/java
#    openssl pkcs12 -export -in ../../../client_cert.pem -inkey ../../../client_key.pem -out client.p12 -name "client" -passout pass:

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENVIRONMENT="${ENVIRONMENT:-dev}"
ENV_FILE="$REPO_ROOT/.env.${ENVIRONMENT}"

# Load environment variables from .env file
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "❌ Error: $ENV_FILE not found"
    echo "Copy .env.template to .env.${ENVIRONMENT} and configure it."
    exit 1
fi

# Fetch credentials from Secrets Manager
echo "Fetching credentials from Secrets Manager..."
SECRET_JSON=$(aws secretsmanager get-secret-value \
    --secret-id "${GATEWAY_SECRET_ID}" \
    --profile "${AWS_PROFILE:-default}" \
    --region "${AWS_REGION:-us-east-1}" \
    --query SecretString --output text)

export CLIENT_ID=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_id'])")
export CLIENT_SECRET=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['client_secret'])")
export OAUTH_TOKEN_URL=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['token_url'])")
export OAUTH_AUDIENCE=$(echo "$SECRET_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin).get('audience',''))")
export GATEWAY_API_URL="${GATEWAY_API_URL}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_DIR="$SCRIPT_DIR/results/$TIMESTAMP"

echo "=== Java Integration Tests ==="
echo "Environment: ${ENVIRONMENT}"
echo "Env file: .env.${ENVIRONMENT}"
echo "Timestamp: $(date)"
echo

mkdir -p "$RESULTS_DIR"

cd "$SCRIPT_DIR/java"
echo "Building Java project..."

if mvn clean compile > "$RESULTS_DIR/java_build.log" 2>&1; then
    echo "✅ Java build successful"
    echo "Running Java tests..."

    if mvn exec:java -Dexec.mainClass="BedrockTester" > "$RESULTS_DIR/java_results.txt" 2>&1; then
        echo "✅ Java tests completed successfully"
        cat "$RESULTS_DIR/java_results.txt"
        exit 0
    else
        echo "❌ Java tests failed"
        cat "$RESULTS_DIR/java_results.txt"
        exit 1
    fi
else
    echo "❌ Java build failed"
    cat "$RESULTS_DIR/java_build.log"
    exit 1
fi
