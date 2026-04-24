#!/usr/bin/env bash
# Lint modified or all markdown files with markdownlint-cli2
#
# Usage:
#   Claude Code Stop hook:  piped JSON on stdin, outputs hookSpecificOutput
#   Git pre-commit hook:    called directly, exits non-zero on lint failure
#   Direct:                 ./scripts/lint-markdown.sh [--pre-commit]

set -euo pipefail

MARKDOWNLINT_CLI2_VERSION="${MARKDOWNLINT_CLI2_VERSION:-0.22.1}"


is_ci() {
  case "${OPENSHIFT_CI:-}" in
    true | 1 | yes | Yes | TRUE) return 0 ;;
  esac
  return 1
}

PRE_COMMIT=false
if [[ "${1:-}" == "--pre-commit" ]]; then
    PRE_COMMIT=true
fi

if ! command -v npx &>/dev/null; then
    exit 0
fi

# Determine working directory
if [ "$PRE_COMMIT" = true ]; then
    CWD="$(git rev-parse --show-toplevel)"
elif [ -t 0 ]; then
    CWD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
    INPUT=$(cat)
    if command -v jq &>/dev/null; then
        CWD=$(echo "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)
    fi
    if [ -z "${CWD:-}" ]; then
        CWD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    fi
fi

cd "$CWD"

# Find .md files to lint based on context
if [ "$PRE_COMMIT" = true ]; then
    ALL_FILES=$(git diff --cached --name-only --diff-filter=ACM -- '*.md' 2>/dev/null || true)
else
    ALL_FILES="**/*.md"
fi

if [ -z "$ALL_FILES" ]; then
    exit 0
fi

# Filter to files that exist (use array for safe handling of special characters)
FILES_TO_LINT=()
while IFS= read -r file; do
    FILES_TO_LINT+=("$file")
done <<< "$ALL_FILES"

if [ "${#FILES_TO_LINT[@]}" -eq 0 ]; then
    exit 0
fi

LINT_EXIT=0
LINT_OUTPUT=$(npx --yes \
    -p "markdownlint-cli2@${MARKDOWNLINT_CLI2_VERSION}" \
    -p markdownlint-cli2-formatter-pretty \
    -p markdownlint-cli2-formatter-junit \
    -p markdownlint-cli2-formatter-json \
    markdownlint-cli2 "${FILES_TO_LINT[@]}" 2>&1) || LINT_EXIT=$?

if [ "$LINT_EXIT" -eq 0 ]; then
    exit 0
fi

# Lint failed: pre-commit always prints to stderr for the human / CI log.
if [[ "$PRE_COMMIT" == true ]] || is_ci; then
    echo "$LINT_OUTPUT" >&2
    echo "" >&2
    echo "Fix markdownlint errors before committing." >&2
    exit 1
fi

# Claude Code Stop hook — structured JSON; errors = parsed markdownlint-cli2-results.json.
# The output is truncated to limit the context message length.
RESULTS_JSON="${CWD}/markdownlint-cli2-results.json"
CONTEXT_MSG='MARKDOWN LINT ERRORS FOUND in modified .md files. Please fix these issues'
if command -v jq &>/dev/null; then
    if [[ -f "$RESULTS_JSON" ]]; then
        jq -cn --slurpfile err "$RESULTS_JSON" --arg msg "$CONTEXT_MSG" '{hookSpecificOutput:{hookEventName:"Stop",errors:$err[0],additionalContext:$msg}}'
    else
        jq -cn --arg lint "$LINT_OUTPUT" --arg msg "$CONTEXT_MSG" '{hookSpecificOutput:{hookEventName:"Stop",errors:{cliOutput:$lint},additionalContext:$msg}}'
    fi
fi

# Clean up temporary files after claude is done, keep them if failure happens when user is running or is in CI.
rm -f markdownlint-cli2-junit.xml markdownlint-cli2-results.json

exit 0
