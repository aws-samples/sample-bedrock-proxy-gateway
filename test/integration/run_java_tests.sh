#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# Prerequisites:
# 1. Create required certificate files in repository root directory:
#    - client_cert.pem (Client certificate for mTLS authentication)
#    - client_key.pem (Private key for mTLS authentication)
#
# 2. Create PKCS#12 keystore file:
#    cd test/integration/java
#    openssl pkcs12 -export -in ../../../client_cert.pem -inkey ../../../client_key.pem -out client.p12 -name "client" -passout pass:
#    cd ../../..
#
# 3. Create a .env file in repository root directory with your client details:
#
#    ENVIRONMENT="dev" # or test
#    CLIENT_ID=<REPLACE-WITH-YOUR-CLIENT-ID>
#    CLIENT_SECRET=<REPLACE-WITH-YOUR-CLIENT-SECRET>

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Load environment variables from .env file in repo root
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
else
    echo "❌ Error: .env file not found at $REPO_ROOT/.env"
    echo "Please create a .env file with CLIENT_ID, CLIENT_SECRET, and ENVIRONMENT variables."
    exit 1
fi

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_DIR="$SCRIPT_DIR/results/$TIMESTAMP"

echo "=== Java Integration Tests ==="
echo "Environment: ${ENVIRONMENT:-dev}"
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
