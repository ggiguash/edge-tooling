#!/usr/bin/env python3
"""Transform raw Jira search results into bugs.json for release planning."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from _jira_transforms import (
    extract_assignee_username,
    extract_display_name,
    is_stale,
    safe_format_date,
    get_nested,
    load_issues,
    write_output,
)

TEAM_COMPONENTS = {
    "Installer / Single Node OpenShift",
    "Two Node with Arbiter",
    "Two Node Fencing",
    "Logical Volume Manager Storage",
    "Bandwidth Reduction",
    "Topology Transition",
    "MicroShift",
    "MicroShift / Networking",
    "MicroShift / Storage",
}


def extract_component(raw):
    """Extract first team-relevant component from the components array."""
    components = raw.get("components") or []
    if isinstance(components, list):
        for comp in components:
            name = comp.get("name", "") if isinstance(comp, dict) else str(comp)
            if name in TEAM_COMPONENTS:
                return name
    return "Unknown"


def transform_bug(raw, today):
    status = get_nested(raw, "status", "name") or ""
    priority = get_nested(raw, "priority", "name") or "Major"
    updated = safe_format_date(raw.get("updated") or raw.get("created") or today, today)
    assignee_raw = raw.get("assignee")

    return {
        "key": raw.get("key", ""),
        "summary": raw.get("summary", ""),
        "status": status,
        "priority": priority,
        "assignee": extract_assignee_username(raw),
        "assignee_display": extract_display_name(assignee_raw, fallback="Unassigned"),
        "component": extract_component(raw),
        "labels": raw.get("labels", []),
        "stale": is_stale(updated, today),
    }


def compute_aggregates(bugs):
    bugs_by_component = {}
    bugs_by_priority = {}
    unassigned_blocker_critical = []

    for bug in bugs:
        key = bug["key"]
        bugs_by_component.setdefault(bug["component"], []).append(key)
        bugs_by_priority.setdefault(bug["priority"], []).append(key)

        if bug["priority"] in ("Blocker", "Critical") and bug["assignee"] is None:
            unassigned_blocker_critical.append(key)

    return {
        "bugs_by_component": bugs_by_component,
        "bugs_by_priority": bugs_by_priority,
        "unassigned_blocker_critical": unassigned_blocker_critical,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Transform Jira search results into bugs.json"
    )
    parser.add_argument("--input", nargs="+", required=True, help="Raw MCP response file(s)")
    parser.add_argument("--output", required=True, help="Output path for bugs.json")
    parser.add_argument("--today", required=True, help="Today's date YYYY-MM-DD")
    args = parser.parse_args()

    raw_issues = load_issues(args.input)
    bugs = []
    skipped_issues = []
    for raw in raw_issues:
        try:
            bugs.append(transform_bug(raw, args.today))
        except Exception as e:
            key = raw.get("key", "unknown")
            skipped_issues.append({"key": key, "error": str(e)})
            print(f"WARNING: skipped {key}: {e}", file=sys.stderr)

    aggregates = compute_aggregates(bugs)

    output = {
        "total_bugs": len(bugs),
        "skipped_issues": skipped_issues,
        "bugs": bugs,
        **aggregates,
    }

    write_output(output, args.output)


if __name__ == "__main__":
    main()
