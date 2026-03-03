#!/bin/bash

# Unit test runner script for Bedrock Gateway
# This script runs unit tests with coverage reporting

set -e

echo "🧪 Running unit tests for Bedrock Gateway..."

# Change to the test/unit directory
cd "$(dirname "$0")"

# Install test dependencies
echo "📦 Installing test dependencies..."
# uv sync --extra test

# Set environment variables to disable telemetry
export OTEL_SDK_DISABLED=true
export OTEL_SERVICE_NAME=test-service
export ENVIRONMENT=test
export OTEL_EXPORTER_OTLP_ENDPOINT=""

# Run tests with coverage
echo "🔍 Running tests with coverage (telemetry disabled)..."
uv run pytest -c pytest.ini

echo "✅ Unit tests completed successfully!"
echo "📊 Coverage report generated in test/unit/htmlcov/index.html"
echo "🔇 Telemetry was disabled during testing to prevent connection errors"
