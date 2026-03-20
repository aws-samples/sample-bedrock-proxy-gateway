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
# 3. Optional mTLS certs in repository root:
#    client_cert.pem, client_key.pem

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ENVIRONMENT="${ENVIRONMENT:-dev}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_DIR="$SCRIPT_DIR/results/$TIMESTAMP"

echo "=== Python Integration Tests ==="
echo "Environment: ${ENVIRONMENT}"
echo "Env file: .env.${ENVIRONMENT}"
echo "Timestamp: $(date)"
echo

mkdir -p "$RESULTS_DIR"

cd "$SCRIPT_DIR/python"
echo "Running Python tests..."

if ENVIRONMENT="$ENVIRONMENT" uv run main.py > "$RESULTS_DIR/python_results.txt" 2>&1; then
    echo "✅ Python tests completed successfully"
    cat "$RESULTS_DIR/python_results.txt"
    exit 0
else
    echo "❌ Python tests failed"
    cat "$RESULTS_DIR/python_results.txt"
    exit 1
fi
