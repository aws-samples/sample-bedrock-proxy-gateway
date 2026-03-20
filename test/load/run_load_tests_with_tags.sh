#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# Load Test Runner Script
# =============================================================================
# Runs Locust load tests with increasing user counts sequentially.
#
# Prerequisites:
#   - .env.dev (or .env.test) at the repository root
#   - GATEWAY_SECRET_ID in .env pointing to Secrets Manager secret
#   - locust installed: pip install locust
#
# Usage: ./run_load_tests_with_tags.sh [runtime_minutes] [verbose]
# Example: ./run_load_tests_with_tags.sh 5
# Example: ./run_load_tests_with_tags.sh 5 verbose
# =============================================================================

set -e

# Load environment from .env.{ENVIRONMENT} at repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENVIRONMENT="${ENVIRONMENT:-dev}"
ENV_FILE="$REPO_ROOT/.env.${ENVIRONMENT}"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "❌ Error: $ENV_FILE not found"
    echo "Copy .env.template to .env.${ENVIRONMENT} and configure it."
    exit 1
fi

# =============================================================================
# CONFIGURATION
# =============================================================================

USER_COUNTS=(8 16 32 50 64)
SPAWN_RATE=10
LOCUST_FILE="locust.py"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check for verbose mode
VERBOSE_MODE=false
if [[ "$2" == "verbose" ]] || [[ "$1" == "verbose" ]]; then
    VERBOSE_MODE=true
    echo -e "${BLUE}🔍 VERBOSE MODE ENABLED${NC}"
    set -x
fi

# Runtime in minutes
DEFAULT_RUNTIME_MINUTES=1
if [[ "$1" =~ ^[0-9]+$ ]]; then
    RUNTIME_MINUTES=$1
else
    RUNTIME_MINUTES=$DEFAULT_RUNTIME_MINUTES
fi

BASE_TIMESTAMP=$(date '+%Y-%m-%d__t_%H_%M_%S')
RESULTS_DIR="./results_${BASE_TIMESTAMP}"
AGGREGATE_CSV="$RESULTS_DIR/aggregate_results.csv"

# =============================================================================
# FUNCTIONS
# =============================================================================

print_header() {
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${BLUE}                              LOAD TEST RUNNER${NC}"
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${YELLOW}Environment:${NC} ${ENVIRONMENT}"
    echo -e "${YELLOW}Gateway URL:${NC} ${GATEWAY_API_URL}"
    echo -e "${YELLOW}Runtime per test:${NC} ${RUNTIME_MINUTES} minutes"
    echo -e "${YELLOW}User counts:${NC} ${USER_COUNTS[*]}"
    echo -e "${YELLOW}Spawn rate:${NC} ${SPAWN_RATE} users/second"
    echo -e "${BLUE}================================================================================================${NC}"
    echo
}

run_single_test() {
    local users=$1
    local test_dir="$RESULTS_DIR/${users}__users"
    local csv_prefix="${users}__users"

    mkdir -p "$test_dir"

    echo -e "${BLUE}🚀 Starting test with ${users} users...${NC}"
    echo -e "${YELLOW}   Duration:${NC} ${RUNTIME_MINUTES} minutes"

    local locust_cmd="locust -f $LOCUST_FILE --users $users --spawn-rate $SPAWN_RATE --run-time ${RUNTIME_MINUTES}m --headless --csv $test_dir/$csv_prefix --only-summary"
    echo -e "${YELLOW}   Command:${NC} $locust_cmd"
    echo

    if eval "$locust_cmd"; then
        echo -e "${GREEN}✅ Test with ${users} users completed successfully${NC}"

        local stats_file="$test_dir/${csv_prefix}_stats.csv"
        if [[ -f "$stats_file" ]]; then
            # Append to aggregate CSV
            if [[ ! -f "$AGGREGATE_CSV" ]] || ! grep -q "Type,Name,Request Count" "$AGGREGATE_CSV"; then
                head -n 1 "$stats_file" > "$AGGREGATE_CSV"
            fi
            echo "# Users: $users, Runtime: ${RUNTIME_MINUTES}m" >> "$AGGREGATE_CSV"
            tail -n +2 "$stats_file" >> "$AGGREGATE_CSV"
            echo "" >> "$AGGREGATE_CSV"
            return 0
        else
            echo -e "${RED}❌ Warning: Results file not found: $stats_file${NC}"
            return 1
        fi
    else
        echo -e "${RED}❌ Test with ${users} users failed${NC}"
        return 1
    fi
}

cleanup_on_error() {
    echo
    echo -e "${RED}❌ Script interrupted or failed (exit code: $?)${NC}"
    echo -e "${YELLOW}   Partial results may be available in: ${RESULTS_DIR}${NC}"
    exit 1
}

# =============================================================================
# MAIN
# =============================================================================

trap cleanup_on_error ERR INT TERM

if [[ ! -f "$LOCUST_FILE" ]]; then
    echo -e "${RED}❌ Error: Locust file not found: $LOCUST_FILE${NC}"
    echo -e "${YELLOW}Run this script from test/load/ directory${NC}"
    exit 1
fi

if ! command -v locust &> /dev/null; then
    echo -e "${RED}❌ Error: Locust is not installed${NC}"
    echo -e "${YELLOW}Install: pip install locust${NC}"
    exit 1
fi

print_header
mkdir -p "$RESULTS_DIR"

successful=0
failed=0

for users in "${USER_COUNTS[@]}"; do
    echo -e "${BLUE}  🔄 Test $((successful + failed + 1))/${#USER_COUNTS[@]}${NC}"
    if run_single_test "$users"; then
        successful=$((successful + 1))
    else
        failed=$((failed + 1))
    fi
    echo
done

echo -e "${BLUE}================================================================================================${NC}"
echo -e "${BLUE}                                    SUMMARY${NC}"
echo -e "${BLUE}================================================================================================${NC}"
echo -e "  Tests run: ${#USER_COUNTS[@]}"
echo -e "  ${GREEN}✅ Successful: ${successful}${NC}"
if [[ $failed -gt 0 ]]; then
    echo -e "  ${RED}❌ Failed: ${failed}${NC}"
fi
echo -e "  Results: ${RESULTS_DIR}/aggregate_results.csv"
echo -e "${BLUE}================================================================================================${NC}"
echo -e "${GREEN}🎉 Load test runner finished${NC}"
