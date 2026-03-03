#!/bin/bash

# =============================================================================
# Load Test Runner Script with Tag Support
# =============================================================================
# This script runs Locust load tests with different user counts sequentially
# and supports filtering by tags for specific tasks. Use verbose command in case
# of problems
#
# Usage: ./run_load_tests_with_tags.sh [runtime_minutes] [tags] [verbose]
# Example: ./run_load_tests_with_tags.sh 5 direct
# Example: ./run_load_tests_with_tags.sh 10 direct,gateway
# Example: ./run_load_tests_with_tags.sh 5 direct verbose
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# CONFIGURATION
# =============================================================================

# User count sequence to test
USER_COUNTS=(8 16 32 50 64)

# Spawn rate (users per second)
SPAWN_RATE=10

# Locust file path
LOCUST_FILE="locust.py"

# Colors for output (define early for debug output)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check for verbose mode
VERBOSE_MODE=false
if [[ "$3" == "verbose" ]] || [[ "$2" == "verbose" ]] || [[ "$1" == "verbose" ]]; then
    VERBOSE_MODE=true
    echo -e "${BLUE}🔍 VERBOSE MODE ENABLED${NC}"
    set -x  # Enable bash debugging
fi

# Debug: Print command line arguments
if [[ "$VERBOSE_MODE" == "true" ]]; then
    echo -e "${BLUE}🔍 DEBUG: Command Line Arguments${NC}"
    echo -e "${YELLOW}   Script name:${NC} $0"
    echo -e "${YELLOW}   Total arguments:${NC} $#"
    echo -e "${YELLOW}   All arguments:${NC} $*"
    echo -e "${YELLOW}   Argument 1 (runtime):${NC} ${1:-"(not provided)"}"
    echo -e "${YELLOW}   Argument 2 (tags):${NC} ${2:-"(not provided)"}"
    echo -e "${YELLOW}   Argument 3 (verbose):${NC} ${3:-"(not provided)"}"
    echo
fi

# Default runtime in minutes (can be overridden by command line argument)
DEFAULT_RUNTIME_MINUTES=1
if [[ "$1" == "verbose" ]]; then
    RUNTIME_MINUTES=$DEFAULT_RUNTIME_MINUTES
elif [[ "$1" =~ ^[0-9]+$ ]]; then
    RUNTIME_MINUTES=$1
else
    RUNTIME_MINUTES=$DEFAULT_RUNTIME_MINUTES
fi

# Tags to include (can be overridden by command line argument)
TAGS_INPUT=""
if [[ "$2" != "verbose" ]] && [[ -n "$2" ]]; then
    TAGS_INPUT="$2"
elif [[ "$1" != "verbose" ]] && [[ "$1" != "" ]] && ! [[ "$1" =~ ^[0-9]+$ ]]; then
    TAGS_INPUT="$1"
fi

# Parse tags into array - split by space or comma
if [[ -n "$TAGS_INPUT" ]]; then
    # Replace commas with spaces and split into array
    TAGS_INPUT_CLEANED=$(echo "$TAGS_INPUT" | tr ',' ' ')
    read -ra TAG_ARRAY <<< "$TAGS_INPUT_CLEANED"
else
    TAG_ARRAY=("")
fi

# Base timestamp for all results directories
BASE_TIMESTAMP=$(date '+%Y-%m-%d__t_%H_%M_%S')

# Global variables for tracking current operation
CURRENT_OPERATION="initialization"
CURRENT_TAG=""
CURRENT_USERS=""
CURRENT_RESULTS_DIR=""

# =============================================================================
# FUNCTIONS
# =============================================================================

print_header() {
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${BLUE}                              LOAD TEST RUNNER (WITH TAGS)${NC}"
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${YELLOW}Runtime per test:${NC} ${RUNTIME_MINUTES} minutes"
    echo -e "${YELLOW}User counts:${NC} ${USER_COUNTS[*]}"
    echo -e "${YELLOW}Spawn rate:${NC} ${SPAWN_RATE} users/second"
    echo -e "${YELLOW}Verbose mode:${NC} $VERBOSE_MODE"
    echo -e "${BLUE}================================================================================================${NC}"
    echo
}

create_directories() {
    local results_dir=$1
    CURRENT_OPERATION="creating directories for $results_dir"
    echo -e "${YELLOW}📁 Creating results directories for: $results_dir${NC}"

    # Create main results directory
    mkdir -p "$results_dir"

    # Create subdirectories for each user count
    for users in "${USER_COUNTS[@]}"; do
        mkdir -p "$results_dir/${users}__users"
    done

    echo -e "${GREEN}✅ Directories created successfully${NC}"
    echo
}

run_single_test() {
    local users=$1
    local current_tag=$2
    local results_dir=$3
    local test_dir="$results_dir/${users}__users"
    local csv_prefix="${users}__users"

    # Update global tracking variables
    CURRENT_OPERATION="running test"
    CURRENT_TAG="$current_tag"
    CURRENT_USERS="$users"
    CURRENT_RESULTS_DIR="$results_dir"

    echo -e "${BLUE}🚀 Starting test with ${users} users (tag: '${current_tag}')...${NC}"
    echo -e "${YELLOW}   Test directory:${NC} $test_dir"
    echo -e "${YELLOW}   Duration:${NC} ${RUNTIME_MINUTES} minutes"

    # Build the locust command
    local locust_cmd="locust -f $LOCUST_FILE --users $users --spawn-rate $SPAWN_RATE --run-time ${RUNTIME_MINUTES}m --headless --csv $test_dir/$csv_prefix --only-summary"

    # Add tags if specified
    if [[ -n "$current_tag" ]]; then
        locust_cmd="$locust_cmd --tags $current_tag"
        echo -e "${YELLOW}   Tags applied:${NC} $current_tag"
    else
        echo -e "${YELLOW}   Tags applied:${NC} (none - all tasks will run)"
    fi

    # echo -e "${YELLOW}   Working directory:${NC} $(pwd)"
    echo -e "${YELLOW}   Locust command executed:${NC} $locust_cmd"
    # echo -e "${YELLOW}   CSV output prefix:${NC} $test_dir/$csv_prefix"
    echo

    # Run the test
    echo -e "${YELLOW}⏳ Test in progress...${NC}"
    CURRENT_OPERATION="executing locust command: $locust_cmd"

    if eval "$locust_cmd"; then
        echo -e "${GREEN}✅ Test with ${users} users completed successfully${NC}"

        CURRENT_OPERATION="checking results file existence"
        # Check if results file exists
        local stats_file="$test_dir/${csv_prefix}_stats.csv"
        if [[ -f "$stats_file" ]]; then
            echo -e "${GREEN}📊 Results file found: $stats_file${NC}"
            return 0
        else
            echo -e "${RED}❌ Warning: Results file not found: $stats_file${NC}"
            echo -e "${YELLOW}   Available files in $test_dir:${NC}"
            ls -la "$test_dir" 2>/dev/null || echo "   Directory does not exist or is empty"
            return 1
        fi
    else
        echo -e "${RED}❌ Test with ${users} users failed${NC}"
        return 1
    fi
}

initialize_aggregate_csv() {
    local results_dir=$1
    local aggregate_csv="$results_dir/aggregate_results.csv"

    CURRENT_OPERATION="initializing aggregate CSV: $aggregate_csv"
    echo -e "${YELLOW}📋 Initializing aggregate results file: $aggregate_csv${NC}"

    # Remove existing aggregate file if it exists
    if [[ -f "$aggregate_csv" ]]; then
        rm "$aggregate_csv"
        echo -e "${YELLOW}   Removed existing aggregate file${NC}"
    fi

    # We'll add the header when we process the first results file
    echo -e "${GREEN}✅ Aggregate file initialized${NC}"
    echo
}

append_results_to_aggregate() {
    local users=$1
    local current_tag=$2
    local results_dir=$3
    local test_dir="$results_dir/${users}__users"
    local csv_prefix="${users}__users"
    local stats_file="$test_dir/${csv_prefix}_stats.csv"
    local aggregate_csv="$results_dir/aggregate_results.csv"

    CURRENT_OPERATION="appending results to aggregate for $users users with tag '$current_tag'"

    # Build the command for logging
    local locust_cmd="locust -f $LOCUST_FILE --users $users --spawn-rate $SPAWN_RATE --run-time ${RUNTIME_MINUTES}m --headless --csv $test_dir/$csv_prefix"
    if [[ -n "$current_tag" ]]; then
        locust_cmd="$locust_cmd --tags $current_tag"
    fi

        if [[ ! -f "$stats_file" ]]; then
        echo -e "${YELLOW}⚠️  Results file not found: $stats_file${NC}"
        echo -e "${YELLOW}   This might be expected if the test failed completely${NC}"

        # Add a note to the aggregate CSV about the missing results
        echo "# MISSING RESULTS - Test failed or was interrupted" >> "$aggregate_csv"
        echo "# Command: $locust_cmd" >> "$aggregate_csv"
        echo "# Test Date: $(date '+%Y-%m-%d %H:%M:%S')" >> "$aggregate_csv"
        echo "# Users: $users, Runtime: ${RUNTIME_MINUTES}m, Spawn Rate: ${SPAWN_RATE}/s, Tags: ${current_tag:-"ALL"}" >> "$aggregate_csv"
        echo "# Status: NO RESULTS FILE GENERATED" >> "$aggregate_csv"
        echo "" >> "$aggregate_csv"

        return 1
    fi

    echo -e "${YELLOW}📊 Appending results for ${users} users (tag: '${current_tag}') to aggregate file...${NC}"

    CURRENT_OPERATION="writing command info to aggregate CSV"
    # Add command info as a comment row
    echo "# Command: $locust_cmd" >> "$aggregate_csv"
    echo "# Test Date: $(date '+%Y-%m-%d %H:%M:%S')" >> "$aggregate_csv"
    echo "# Users: $users, Runtime: ${RUNTIME_MINUTES}m, Spawn Rate: ${SPAWN_RATE}/s, Tags: ${current_tag:-"ALL"}" >> "$aggregate_csv"

    CURRENT_OPERATION="checking and adding CSV header"
    # Check if this is the first results file (to add header)
    if [[ ! -s "$aggregate_csv" ]] || ! grep -q "Type,Name,Request Count" "$aggregate_csv"; then
        # Add the header from the first results file
        head -n 1 "$stats_file" >> "$aggregate_csv"
        echo -e "${YELLOW}   Added CSV header${NC}"
    fi

    CURRENT_OPERATION="appending data rows to aggregate CSV"
    # Add all data rows (skip header)
    tail -n +2 "$stats_file" >> "$aggregate_csv"

    # Add separator for readability
    echo "" >> "$aggregate_csv"

    echo -e "${GREEN}✅ Results appended successfully${NC}"
    echo
}

print_summary() {
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${BLUE}                                    TEST SUMMARY${NC}"
    echo -e "${BLUE}================================================================================================${NC}"
    echo -e "${GREEN}✅ All load tests completed successfully!${NC}"
    echo
    echo -e "${YELLOW}Results summary:${NC}"
    echo -e "  • Total tag groups tested: ${#TAG_ARRAY[@]}"
    echo -e "  • Total tests run: $((${#TAG_ARRAY[@]} * ${#USER_COUNTS[@]}))"
    echo -e "  • User counts tested per tag: ${USER_COUNTS[*]}"
    echo -e "  • Runtime per test: ${RUNTIME_MINUTES} minutes"
    echo -e "  • Total runtime: $((${#TAG_ARRAY[@]} * ${#USER_COUNTS[@]} * RUNTIME_MINUTES)) minutes"
    echo
    echo -e "${YELLOW}Tag groups and results:${NC}"
    for i in "${!TAG_ARRAY[@]}"; do
        current_tag="${TAG_ARRAY[i]}"
        if [[ -n "$current_tag" ]]; then
            current_results_dir="./results_${BASE_TIMESTAMP}_${current_tag}"
            tag_display="'$current_tag'"
        else
            current_results_dir="./results_${BASE_TIMESTAMP}"
            tag_display="(all tasks)"
        fi
        echo -e "  • Tag $((i+1)): ${tag_display} -> ${current_results_dir}/aggregate_results.csv"
    done
    echo
    echo -e "${BLUE}================================================================================================${NC}"
}

cleanup_on_error() {
    local exit_code=$?
    echo
    echo -e "${RED}❌ Script interrupted or failed${NC}"
    echo -e "${RED}📍 FAILURE DETAILS:${NC}"
    echo -e "${YELLOW}   Exit code:${NC} $exit_code"
    echo -e "${YELLOW}   Current operation:${NC} $CURRENT_OPERATION"
    echo -e "${YELLOW}   Current tag:${NC} ${CURRENT_TAG:-"(none)"}"
    echo -e "${YELLOW}   Current users:${NC} ${CURRENT_USERS:-"(none)"}"
    echo -e "${YELLOW}   Current results dir:${NC} ${CURRENT_RESULTS_DIR:-"(none)"}"
    echo -e "${YELLOW}   Working directory:${NC} $(pwd)"
    echo -e "${YELLOW}   Timestamp:${NC} $(date '+%Y-%m-%d %H:%M:%S')"

    if [[ -n "$CURRENT_RESULTS_DIR" ]]; then
        echo -e "${YELLOW}   Partial results may be available in:${NC} $CURRENT_RESULTS_DIR"
    fi

    # Show recent command history if verbose mode is enabled
    if [[ "$VERBOSE_MODE" == "true" ]]; then
        echo -e "${YELLOW}   Recent bash trace should be visible above${NC}"
    fi

    echo -e "${BLUE}💡 TIP: Run with 'verbose' parameter for more detailed debugging${NC}"
    echo -e "${BLUE}   Example: $0 $1 $2 verbose${NC}"
    exit 1
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

# Set up error handling
trap cleanup_on_error ERR INT TERM

CURRENT_OPERATION="validating prerequisites"

# Validate prerequisites
if [[ ! -f "$LOCUST_FILE" ]]; then
    echo -e "${RED}❌ Error: Locust file not found: $LOCUST_FILE${NC}"
    echo -e "${YELLOW}Please ensure you're running this script from the correct directory${NC}"
    echo -e "${YELLOW}Current directory: $(pwd)${NC}"
    echo -e "${YELLOW}Files in current directory:${NC}"
    ls -la
    exit 1
fi

# Check if locust is installed
if ! command -v locust &> /dev/null; then
    echo -e "${RED}❌ Error: Locust is not installed or not in PATH${NC}"
    echo -e "${YELLOW}Please install locust: pip install locust${NC}"
    exit 1
fi

CURRENT_OPERATION="printing header and setup"

# Print header and setup
print_header

# Run tests sequentially by tag groups
echo -e "${BLUE}🎯 Starting sequential load tests...${NC}"
echo

total_successful_tests=0
total_failed_tests=0

CURRENT_OPERATION="starting tag loop"

# Loop through each tag group
for i in "${!TAG_ARRAY[@]}"; do
    current_tag="${TAG_ARRAY[i]}"

    CURRENT_OPERATION="setting up tag group $((i+1))"
    CURRENT_TAG="$current_tag"

    # Create results directory for this tag
    if [[ -n "$current_tag" ]]; then
        current_results_dir="./results_${BASE_TIMESTAMP}_${current_tag}"
        tag_display="'$current_tag'"
    else
        current_results_dir="./results_${BASE_TIMESTAMP}"
        tag_display="(all tasks)"
    fi

    CURRENT_RESULTS_DIR="$current_results_dir"

    echo -e "${BLUE}▶️  Tag Group $((i+1))/${#TAG_ARRAY[@]}: ${tag_display}${NC}"
    echo -e "${YELLOW}   Results directory: ${current_results_dir}${NC}"
    echo

    # Setup directories and aggregate file for this tag group
    create_directories "$current_results_dir"
    initialize_aggregate_csv "$current_results_dir"

    successful_tests=0
    failed_tests=0

    CURRENT_OPERATION="starting user count loop for tag $tag_display"

    # Run tests for all user counts with current tag
    for users in "${USER_COUNTS[@]}"; do
        echo -e "${BLUE}  🔄 Test $(($successful_tests + $failed_tests + 1))/${#USER_COUNTS[@]} for tag ${tag_display}${NC}"

                CURRENT_OPERATION="running test $users users for tag $tag_display"

        # Run the test and capture the result
        test_success=false
        if run_single_test "$users" "$current_tag" "$current_results_dir"; then
            test_success=true
        fi

        # Always try to append results, even if test failed (in case partial results exist)
        CURRENT_OPERATION="appending results for $users users (test_success: $test_success)"
        append_success=false
        if append_results_to_aggregate "$users" "$current_tag" "$current_results_dir"; then
            append_success=true
        fi

        # Update counters based on both test and append success
        if [[ "$test_success" == "true" ]] && [[ "$append_success" == "true" ]]; then
            # Test ran successfully and results were appended
            successful_tests=$((successful_tests + 1))
            total_successful_tests=$((total_successful_tests + 1))
            echo -e "${GREEN}✅ Test and results aggregation both successful${NC}"
        elif [[ "$test_success" == "true" ]] && [[ "$append_success" == "false" ]]; then
            # Test ran but couldn't append results
            failed_tests=$((failed_tests + 1))
            total_failed_tests=$((total_failed_tests + 1))
            echo -e "${YELLOW}⚠️  Test successful but failed to aggregate results${NC}"
        elif [[ "$test_success" == "false" ]] && [[ "$append_success" == "true" ]]; then
            # Test failed but we got some results
            failed_tests=$((failed_tests + 1))
            total_failed_tests=$((total_failed_tests + 1))
            echo -e "${YELLOW}⚠️  Test failed but partial results were captured${NC}"
        else
            # Both test and append failed
            failed_tests=$((failed_tests + 1))
            total_failed_tests=$((total_failed_tests + 1))
            echo -e "${RED}❌ Both test and results aggregation failed${NC}"
        fi

        echo -e "${YELLOW}  Progress for ${tag_display}: ${successful_tests} successful, ${failed_tests} failed${NC}"
        echo
    done

    CURRENT_OPERATION="completing tag group $tag_display"

    # Summary for this tag group
    if [[ $failed_tests -eq 0 ]]; then
        echo -e "${GREEN}✅ All tests completed successfully for tag ${tag_display}${NC}"
    else
        echo -e "${YELLOW}⚠️  Tag ${tag_display} completed with ${failed_tests} failures${NC}"
    fi
    echo -e "${YELLOW}   Results saved in: ${current_results_dir}${NC}"
    echo
done

CURRENT_OPERATION="printing final summary"

# Print final summary
if [[ $total_failed_tests -eq 0 ]]; then
    print_summary
else
    echo -e "${YELLOW}⚠️  Tests completed with ${total_failed_tests} failures${NC}"
    echo -e "${GREEN}✅ Successful tests: ${total_successful_tests}${NC}"
    echo -e "${RED}❌ Test with errors: ${total_failed_tests}${NC}"
    echo -e "${YELLOW}Check individual test directories for details${NC}"
fi

echo -e "${GREEN}🎉 Load test runner finished${NC}"
