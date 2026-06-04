#!/usr/bin/bash
set -euo pipefail

# Check if a JIRA issue has a GitHub PR linked.
#
# Searches GitHub via gh CLI for PRs whose title contains the JIRA key
# in the openshift/microshift repo. Checks both open and merged PRs.
# CLOSED (unmerged) PRs do not count as a match.
#
# Usage:
#   check-jira-pr-links.sh <jira-key>
#
# Exit codes:
#   0 — PR found (prints PR URL(s) to stdout)
#   1 — no PR found
#   2 — usage error

usage() {
    echo "Usage: $(basename "$0") <jira-key>" >&2
    exit 2
}

[[ ${#} -ne 1 ]] && usage

JIRA_KEY="${1}"

gh_urls=$(gh pr list --repo openshift/microshift --search "${JIRA_KEY} in:title" --state open --json url --jq '.[].url' 2>/dev/null || true)
gh_urls+=$'\n'$(gh pr list --repo openshift/microshift --search "${JIRA_KEY} in:title" --state merged --json url --jq '.[].url' 2>/dev/null || true)
gh_urls=$(echo "${gh_urls}" | sed '/^$/d')
if [[ -n "${gh_urls}" ]]; then
    echo "${gh_urls}"
    exit 0
fi

exit 1
