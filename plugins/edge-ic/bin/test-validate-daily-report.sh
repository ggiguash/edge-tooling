#!/usr/bin/bash
# Test suite for validate-daily-report.sh
# Runs validation against test fixtures and verifies expected outcomes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$SCRIPT_DIR/validate-daily-report.sh"
FIXTURES_DIR="$SCRIPT_DIR/../references/test-fixtures"

TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    TESTS_PASSED=$((TESTS_PASSED + 1))
}

fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    TESTS_FAILED=$((TESTS_FAILED + 1))
}

info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

run_test() {
    local test_name="$1"
    local fixture="$2"
    local expected_exit="$3"
    local description="$4"

    TESTS_RUN=$((TESTS_RUN + 1))

    echo ""
    info "Test $TESTS_RUN: $test_name"
    echo "  Description: $description"
    echo "  Fixture: $fixture"
    echo "  Expected exit code: $expected_exit"
    echo "  ---"

    # Run validator and capture exit code
    set +e
    output=$("$VALIDATOR" "$FIXTURES_DIR/$fixture" 2>&1)
    exit_code=$?
    set -e

    # Check exit code matches expectation
    if [ "$exit_code" -eq "$expected_exit" ]; then
        pass "$test_name (exit code: $exit_code)"
    else
        fail "$test_name (expected exit $expected_exit, got $exit_code)"
        echo "  Output:"
        printf '%s\n' "$output" | while IFS= read -r line; do printf '    %s\n' "$line"; done
    fi
}

run_test_strict() {
    local test_name="$1"
    local fixture="$2"
    local expected_exit="$3"
    local description="$4"

    TESTS_RUN=$((TESTS_RUN + 1))

    echo ""
    info "Test $TESTS_RUN: $test_name (STRICT mode)"
    echo "  Description: $description"
    echo "  Fixture: $fixture"
    echo "  Expected exit code: $expected_exit"
    echo "  ---"

    # Run validator in strict mode and capture exit code
    set +e
    output=$(STRICT=1 "$VALIDATOR" "$FIXTURES_DIR/$fixture" 2>&1)
    exit_code=$?
    set -e

    # Check exit code matches expectation
    if [ "$exit_code" -eq "$expected_exit" ]; then
        pass "$test_name (exit code: $exit_code)"
    else
        fail "$test_name (expected exit $expected_exit, got $exit_code)"
        echo "  Output:"
        printf '%s\n' "$output" | while IFS= read -r line; do printf '    %s\n' "$line"; done
    fi
}

# Verify validator exists
if [ ! -x "$VALIDATOR" ]; then
    echo -e "${RED}ERROR${NC}: Validator script not found or not executable: $VALIDATOR"
    exit 1
fi

# Verify fixtures directory exists
if [ ! -d "$FIXTURES_DIR" ]; then
    echo -e "${RED}ERROR${NC}: Fixtures directory not found: $FIXTURES_DIR"
    exit 1
fi

echo "========================================"
echo "Daily Report Validator Test Suite"
echo "========================================"
echo "Validator: $VALIDATOR"
echo "Fixtures:  $FIXTURES_DIR"
echo ""

# Test 1: Valid report should pass
run_test \
    "valid-report" \
    "valid-report.txt" \
    0 \
    "Properly formatted report with header, emojis, and Jira URLs"

# Test 2: Missing header should fail
run_test \
    "invalid-no-header" \
    "invalid-no-header.txt" \
    1 \
    "Report without header line should fail"

# Test 3: Markdown checkboxes should fail
run_test \
    "invalid-markdown-checkboxes" \
    "invalid-markdown-checkboxes.txt" \
    1 \
    "Report using markdown checkboxes instead of emojis should fail"

# Test 4: Code blocks should fail
run_test \
    "invalid-code-blocks" \
    "invalid-code-blocks.txt" \
    1 \
    "Report with markdown code blocks should fail"

# Test 5: Missing Jira URL should warn (exit code 2 in normal mode)
run_test \
    "warning-missing-jira-url" \
    "warning-missing-jira-url.txt" \
    2 \
    "Report with Jira tickets missing URLs should warn (exit code 2)"

# Test 6: Missing Jira URL should fail in strict mode
run_test_strict \
    "warning-missing-jira-url-strict" \
    "warning-missing-jira-url.txt" \
    1 \
    "Report with Jira tickets missing URLs should fail in strict mode"

# Test 7: Too many bullets should warn (exit code 2 in normal mode)
run_test \
    "warning-too-many-bullets" \
    "warning-too-many-bullets.txt" \
    2 \
    "Report with >20 bullets should warn (exit code 2)"

# Test 8: Too many bullets should fail in strict mode
run_test_strict \
    "warning-too-many-bullets-strict" \
    "warning-too-many-bullets.txt" \
    1 \
    "Report with >20 bullets should fail in strict mode"

# Test 9: Non-existent file should fail
run_test \
    "non-existent-file" \
    "does-not-exist.txt" \
    1 \
    "Validator should fail gracefully for missing file"

# Summary
echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo "Tests run:    $TESTS_RUN"
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ $TESTS_FAILED test(s) failed${NC}"
    exit 1
fi
