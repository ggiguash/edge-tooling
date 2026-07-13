#!/usr/bin/bash
set -euo pipefail -E

# PreToolUse (Bash) hook enforcing the fix-test-bugs dry-run switch.
# See SKILL.md Notes for the full two-layer enforcement design.

SUBMIT_RE="fix-test-bugs\.sh[\"'[:space:]]+submit([\"'[:space:];&|]|\$)"
CLEANUP_RE="fix-test-bugs\.sh[\"'[:space:]]+cleanup-stale-branches([\"'[:space:];&|]|\$)"
GIT_PUSH_RE='git.*push'
GH_PR_CREATE_RE='gh.*pr.*create'

deny() {
    # printf, not jq: the deny path must work even when jq is broken or
    # missing (fail-closed). Reasons are static strings from this script.
    local reason="${1//\"/\\\"}"
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' \
        "${reason}"
}

main() {
    if [[ "${MICROSHIFT_CI_DRY_RUN:-}" != "1" ]]; then
        return 0
    fi

    # From here on any unexpected error must deny, not silently allow: a
    # non-2 exit code is a NON-blocking hook error to Claude Code
    trap 'deny "fix-test-bugs guard hit an unexpected error; publishing commands are blocked (fail-closed)"; exit 0' ERR

    local command
    command=$(jq -r '.tool_input.command // empty' 2>/dev/null) \
        || { deny "fix-test-bugs guard could not parse the hook payload (is jq installed?); publishing commands are blocked (fail-closed)"; return 0; }
    [[ -z "${command}" ]] && return 0

    local blocked=""
    if [[ "${command}" =~ ${SUBMIT_RE} ]]; then
        blocked="the fix-test-bugs.sh submit subcommand"
    elif [[ "${command}" =~ ${CLEANUP_RE} ]]; then
        blocked="the fix-test-bugs.sh cleanup-stale-branches subcommand"
    elif [[ "${command}" =~ ${GIT_PUSH_RE} ]] || [[ "${command}" =~ ${GH_PR_CREATE_RE} ]]; then
        blocked="'git push'/'gh pr create'"
    fi
    [[ -z "${blocked}" ]] && return 0

    deny "The microshift-ci plugin blocks ${blocked} because dry-run mode is active (MICROSHIFT_CI_DRY_RUN=1). Unset the variable to allow publishing."
}

main "${@}"
