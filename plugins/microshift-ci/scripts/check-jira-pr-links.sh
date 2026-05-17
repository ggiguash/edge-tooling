#!/usr/bin/bash
set -euo pipefail

# Check if a JIRA issue has a GitHub PR linked.
#
# Two-source check:
#   1. Parse JIRA changelog JSON (from jira_batch_get_changelogs) for
#      RemoteWorkItemLink entries referencing GitHub PRs. Accounts for
#      both additions and removals to determine current state.
#   2. If no JIRA link found, fall back to searching GitHub via gh CLI
#      for PRs whose title or branch contains the JIRA key.
#
# Usage:
#   check-jira-pr-links.sh <changelog.json> <jira-key>
#
# Exit codes:
#   0 — PR found (prints PR URL to stdout)
#   1 — no PR found
#   2 — usage error

usage() {
    echo "Usage: $(basename "$0") <changelog.json> <jira-key>" >&2
    exit 2
}

[[ ${#} -ne 2 ]] && usage

CHANGELOG_FILE="${1}"
JIRA_KEY="${2}"

[[ -f "${CHANGELOG_FILE}" ]] || { echo "Error: file not found: ${CHANGELOG_FILE}" >&2; exit 2; }

# --- Source 1: JIRA changelog ---
tmpout=$(mktemp)
trap 'rm -f "${tmpout}"' EXIT

python3 - "${CHANGELOG_FILE}" > "${tmpout}" <<'PYEOF' && rc=0 || rc=$?
import json
import re
import sys

changelog_file = sys.argv[1]

with open(changelog_file) as f:
    data = json.load(f)

changelogs = list(reversed(data[0].get("changelogs", []))) if data else []

url_pattern = re.compile(r'github\.com/([^/]+)/([^/]+)/pull/(\d+)')
shorthand_pattern = re.compile(r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(\d+)')
active_prs = {}

def extract_pr_url(text):
    m = url_pattern.search(text)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}/pull/{m.group(3)}"
    m = shorthand_pattern.search(text)
    if m:
        return f"https://github.com/{m.group(1)}/pull/{m.group(2)}"
    return None

for entry in changelogs:
    for item in entry.get("items", []):
        if item.get("field") != "RemoteWorkItemLink":
            continue
        to_str = item.get("to_string", "") or ""
        from_str = item.get("from_string", "") or ""
        link_id = item.get("to_id") or item.get("from_id", "")

        if to_str:
            pr_url = extract_pr_url(to_str)
            if pr_url:
                active_prs[link_id] = pr_url

        if from_str and not to_str:
            rm_id = item.get("from_id", "")
            if rm_id in active_prs:
                del active_prs[rm_id]

if active_prs:
    for pr_url in active_prs.values():
        print(pr_url)
    sys.exit(0)
else:
    sys.exit(1)
PYEOF

if [[ ${rc} -eq 0 ]]; then
    # Verify each JIRA-linked PR is OPEN or MERGED on GitHub (not CLOSED without merge)
    local_found=""
    while IFS= read -r pr_url; do
        [[ -z "${pr_url}" ]] && continue
        pr_state=$(gh pr view "${pr_url}" --json state --jq '.state' 2>/dev/null || true)
        if [[ "${pr_state}" == "OPEN" || "${pr_state}" == "MERGED" ]]; then
            local_found="${local_found}${pr_url}"$'\n'
        fi
    done < "${tmpout}"
    local_found="${local_found%$'\n'}"
    if [[ -n "${local_found}" ]]; then
        echo "${local_found}"
        exit 0
    fi
fi

# --- Source 2: GitHub fallback ---
gh_urls=$(gh pr list --repo openshift/microshift --search "${JIRA_KEY}" --state open --state merged --json url --jq '.[].url' 2>/dev/null || true)
if [[ -n "${gh_urls}" ]]; then
    echo "${gh_urls}"
    exit 0
fi

exit 1
