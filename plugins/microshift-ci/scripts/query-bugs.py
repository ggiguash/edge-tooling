#!/usr/bin/env python3
"""
Query JIRA for duplicate/regression bugs matching CI failure candidates.

Reads candidate JSON files produced by search-bugs.py, runs JQL searches
against the JIRA REST API, and writes per-source bug mapping files consumed
by search-bugs.py --merge and the create-bugs skill.

Usage:
    query-bugs.py <candidates1.json> [<candidates2.json> ...] --workdir DIR

Environment:
    JIRA_URL          Base URL (default: https://redhat.atlassian.net)
    JIRA_USERNAME     User email for Basic auth
    JIRA_API_TOKEN    Atlassian API token

Output:
    ${WORKDIR}/analyze-ci-bugs-<source>.json   (one per input file)
"""

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_JIRA_URL = "https://redhat.atlassian.net"
SEARCH_PATH = "/rest/api/2/search"
MAX_WORKERS = 4

PROJECT_SCOPE = (
    '((project = OCPBUGS AND component = MicroShift) OR project = USHIFT)'
)


# ---------------------------------------------------------------------------
# HTTP session
# ---------------------------------------------------------------------------

def _create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# JIRA client
# ---------------------------------------------------------------------------

class JiraClient:
    def __init__(self, base_url, username, token):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, token)
        self.session = _create_session()
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search(self, jql, fields="summary,status,assignee,updated", max_results=5, start_at=0):
        resp = self.session.get(
            f"{self.base_url}{SEARCH_PATH}",
            params={
                "jql": jql,
                "maxResults": max_results,
                "startAt": start_at,
                "fields": fields,
            },
            headers=self.headers,
            auth=self.auth,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def search_all(self, jql, fields="summary,status,assignee,updated", page_size=50):
        issues = []
        start = 0
        while True:
            data = self.search(jql, fields=fields, max_results=page_size, start_at=start)
            batch = data.get("issues", [])
            if not batch:
                break
            issues.extend(batch)
            if start + len(batch) >= data.get("total", 0):
                break
            start += len(batch)
        return issues


# ---------------------------------------------------------------------------
# Issue parsing helpers
# ---------------------------------------------------------------------------

def _parse_issue(issue, extra_fields=()):
    fields = issue.get("fields", {})
    assignee = fields.get("assignee") or {}
    status = fields.get("status") or {}
    result = {
        "key": issue["key"],
        "summary": fields.get("summary", ""),
        "status": status.get("name", ""),
        "assignee": assignee.get("displayName", "Unassigned"),
        "updated": fields.get("updated", "")[:10],
    }
    if "priority" in extra_fields:
        priority = fields.get("priority") or {}
        result["priority"] = priority.get("name", "")
    if "created" in extra_fields:
        result["created"] = fields.get("created", "")[:10]
    return result


# ---------------------------------------------------------------------------
# Per-candidate search
# ---------------------------------------------------------------------------

def _escape_jql(text):
    """Strip characters that break JQL text~ queries."""
    return text.replace('"', '').replace('\\', '')


def _search_candidate(client, candidate):
    """Run all searches for a single candidate. Returns (duplicates, regressions)."""
    keywords = candidate.get("keywords", [])
    test_ids = candidate.get("test_ids", [])
    sig = candidate.get("error_signature", "?")[:60]

    all_issues = {}  # key -> parsed issue (open, for duplicates)

    # Search A — keyword search (up to 3 keywords, one query each)
    for kw in keywords[:3]:
        jql = (
            f'{PROJECT_SCOPE} AND issuetype = Bug '
            f'AND text ~ "{_escape_jql(kw)}" '
            f'AND status not in (Closed, Verified)'
        )
        data = client.search(jql, max_results=5)
        for issue in data.get("issues", []):
            parsed = _parse_issue(issue)
            all_issues[parsed["key"]] = parsed

    # Search B — test ID search (bare + OCP-prefixed)
    for tid in test_ids:
        for term in [tid, f"OCP-{tid}"]:
            jql = (
                f'{PROJECT_SCOPE} AND issuetype = Bug '
                f'AND text ~ "{_escape_jql(term)}" '
                f'AND status not in (Closed, Verified)'
            )
            data = client.search(jql, max_results=5)
            for issue in data.get("issues", []):
                parsed = _parse_issue(issue)
                all_issues[parsed["key"]] = parsed

    duplicates = list(all_issues.values())

    # Search C — regression check (closed/verified issues, one query per keyword)
    regression_issues = {}
    for kw in keywords[:2]:
        jql = (
            f'{PROJECT_SCOPE} AND issuetype = Bug '
            f'AND text ~ "{_escape_jql(kw)}" '
            f'AND status in (Closed, Verified) '
            f'ORDER BY updated DESC'
        )
        data = client.search(jql, max_results=5)
        for issue in data.get("issues", []):
            parsed = _parse_issue(issue)
            regression_issues[parsed["key"]] = parsed
    regressions = list(regression_issues.values())

    return duplicates, regressions


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def query_source(client, source_data, open_bugs):
    """Query JIRA for all candidates in a source file. Returns the mapping dict."""
    source = source_data["source"]
    candidates_in = source_data.get("candidates", [])
    candidates_out = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {}
        for i, cand in enumerate(candidates_in):
            futures[pool.submit(_search_candidate, client, cand)] = (i, cand)

        results = [None] * len(candidates_in)
        for future in as_completed(futures):
            idx, cand = futures[future]
            duplicates, regressions = future.result()
            results[idx] = (duplicates, regressions)

    for cand, (duplicates, regressions) in zip(candidates_in, results):
        n_dup = len(duplicates)
        n_reg = len(regressions)
        sig = cand.get("error_signature", "?")[:60]
        if n_dup or n_reg:
            print(f"  \"{sig}\" — {n_dup} duplicates, {n_reg} regressions", file=sys.stderr)

        candidates_out.append({
            "error_signature": cand["error_signature"],
            "severity": cand["severity"],
            "failure_type": cand.get("failure_type", "test"),
            "step_name": cand.get("step_name", ""),
            "affected_jobs": cand.get("affected_jobs", 0),
            "duplicates": duplicates,
            "regressions": regressions,
        })

    return {
        "source": source,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "candidates": candidates_out,
        "open_bugs": open_bugs,
    }


def fetch_open_bugs(client):
    """Fetch all open AI-generated bugs (global, once per run)."""
    jql = (
        'project = USHIFT AND issuetype = Bug '
        'AND labels = microshift-ci-ai-generated '
        'AND status not in (Closed, Verified) '
        'ORDER BY updated DESC'
    )
    issues = client.search_all(
        jql,
        fields="summary,status,priority,assignee,created,updated",
        page_size=50,
    )
    return [_parse_issue(issue, extra_fields=("priority", "created")) for issue in issues]


def main():
    args = sys.argv[1:]
    workdir = None
    candidate_files = []

    i = 0
    while i < len(args):
        if args[i] == "--workdir":
            if i + 1 >= len(args):
                print("Error: --workdir requires an argument", file=sys.stderr)
                sys.exit(1)
            workdir = args[i + 1]
            i += 2
        elif args[i].startswith("-"):
            print(f"Unknown option: {args[i]}", file=sys.stderr)
            sys.exit(1)
        else:
            candidate_files.append(args[i])
            i += 1

    if not candidate_files:
        print(
            "Usage: query-bugs.py <candidates1.json> [<candidates2.json> ...] --workdir DIR\n"
            "\n"
            "Environment variables:\n"
            "  JIRA_URL          Base URL (default: https://redhat.atlassian.net)\n"
            "  JIRA_USERNAME     User email for Basic auth\n"
            "  JIRA_API_TOKEN    Atlassian API token",
            file=sys.stderr,
        )
        sys.exit(1)

    if workdir is None:
        print("Error: --workdir DIR is required", file=sys.stderr)
        sys.exit(1)

    # Validate inputs
    for filepath in candidate_files:
        if not os.path.isfile(filepath):
            print(f"Error: file not found: {filepath}", file=sys.stderr)
            sys.exit(1)

    if not os.path.isdir(workdir):
        print(f"Error: work directory does not exist: {workdir}", file=sys.stderr)
        sys.exit(1)

    # Load all candidate files
    sources = []
    for filepath in candidate_files:
        with open(filepath, "r") as f:
            sources.append(json.load(f))

    total_candidates = sum(len(s.get("candidates", [])) for s in sources)
    print(
        f"Loaded {total_candidates} candidates from {len(sources)} source(s)",
        file=sys.stderr,
    )

    # Cache check: skip JIRA queries if output files already cover all candidates
    cached_sigs = set()
    cache_valid = True
    for source_data in sources:
        output_path = os.path.join(workdir, f"analyze-ci-bugs-{source_data['source']}.json")
        if not os.path.isfile(output_path):
            cache_valid = False
            break
        with open(output_path, "r") as f:
            cached = json.load(f)
        for cand in cached.get("candidates", []):
            cached_sigs.add(cand.get("error_signature"))

    if cache_valid:
        all_covered = all(
            c.get("error_signature") in cached_sigs
            for s in sources for c in s.get("candidates", [])
        )
        if all_covered:
            print(
                "Using cached Jira search results from prior run.\n"
                "To force fresh Jira searches, delete the bug mapping files:\n"
                f"  rm {workdir}/analyze-ci-bugs-*.json",
                file=sys.stderr,
            )
            sys.exit(0)

    # Validate credentials (only needed when running fresh queries)
    jira_url = os.environ.get("JIRA_URL", DEFAULT_JIRA_URL)
    username = os.environ.get("JIRA_USERNAME", "")
    token = os.environ.get("JIRA_API_TOKEN", "")

    missing = []
    if not username:
        missing.append("JIRA_USERNAME")
    if not token:
        missing.append("JIRA_API_TOKEN")
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    total_queries = sum(
        min(len(c.get("keywords", [])), 3) + 2 * len(c.get("test_ids", []))
        + min(len(c.get("keywords", [])), 2)
        for s in sources for c in s.get("candidates", [])
    )

    client = JiraClient(jira_url, username, token)

    # Fetch open AI-generated bugs (once)
    print("Fetching open AI-generated bugs...", file=sys.stderr, end=" ")
    try:
        open_bugs = fetch_open_bugs(client)
    except requests.RequestException as e:
        print(f"failed: {e}", file=sys.stderr)
        sys.exit(2)
    print(f"{len(open_bugs)} found", file=sys.stderr)

    # Process each source
    print(
        f"Searching JIRA for duplicates... (~{total_queries} queries across {total_candidates} candidates)",
        file=sys.stderr,
    )
    for source_data in sources:
        source = source_data["source"]
        n = len(source_data.get("candidates", []))
        print(f"  Source {source}: {n} candidates", file=sys.stderr)

        try:
            result = query_source(client, source_data, open_bugs)
        except requests.RequestException as e:
            print(f"Error: JIRA search failed for source '{source}': {e}", file=sys.stderr)
            sys.exit(2)

        output_path = os.path.join(workdir, f"analyze-ci-bugs-{source}.json")
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Written: {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
