#!/usr/bin/env python3
"""Filter and reshape Red Hat container catalog image data.

Reads raw API JSON from stdin, applies version-boundary-aware filtering,
and outputs structured JSON to stdout.  Also importable for the shared
``tag_matches_release`` helper used by create-report.py.

Usage:
    curl ... | python3 filter_images.py tags  [--tag 4.18]
    curl ... | python3 filter_images.py images [--tag 4.18]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone


_RELEASE_PATTERN_CACHE = {}


def tag_matches_release(tag, release):
    """Check whether *tag* contains *release* at a version boundary.

    Requires a non-digit (or string edge) on both sides of *release* so
    that ``4.2`` matches ``v4.2.1`` but **not** ``v4.20.1``.
    """
    pat = _RELEASE_PATTERN_CACHE.get(release)
    if pat is None:
        pat = re.compile(r'(?:^|(?<!\d))' + re.escape(release) + r'(?!\d)')
        _RELEASE_PATTERN_CACHE[release] = pat
    return bool(pat.search(tag))


def _current_freshness_grade(grades):
    """Select the freshness grade whose date range contains *now*."""
    now = datetime.now(timezone.utc)
    for g in (grades or []):
        start = g.get("start_date") or "1970-01-01T00:00:00+00:00"
        end = g.get("end_date") or "9999-12-31T23:59:59+00:00"
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            if start_dt <= now < end_dt:
                return g.get("grade")
        except (ValueError, TypeError):
            continue
    return None


def filter_tags(data, tag_filter=""):
    """Return sorted unique tag names, optionally filtered by release."""
    tags = set()
    for entry in data.get("data", []):
        for repo in entry.get("repositories", []):
            for t in repo.get("tags", []):
                tags.add(t["name"])
    result = sorted(tags)
    if tag_filter:
        result = [t for t in result if tag_matches_release(t, tag_filter)]
    return result


def filter_images(data, tag_filter=""):
    """Filter and reshape images into the structure expected downstream.

    Output per image::

        {_id, tags, architecture, freshness_grade,
         creation_date, last_update_date}
    """
    result = []
    for entry in data.get("data", []):
        all_tags = [
            t["name"]
            for repo in entry.get("repositories", [])
            for t in repo.get("tags", [])
        ]
        if tag_filter and not any(tag_matches_release(t, tag_filter) for t in all_tags):
            continue

        result.append({
            "_id": entry.get("_id"),
            "tags": sorted(set(all_tags), key=len),
            "architecture": entry.get("architecture"),
            "freshness_grade": _current_freshness_grade(entry.get("freshness_grades")),
            "creation_date": entry.get("creation_date"),
            "last_update_date": entry.get("last_update_date"),
        })

    result.sort(key=lambda x: (x["tags"][0] if x["tags"] else "", x.get("architecture") or ""))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["tags", "images"])
    parser.add_argument("--tag", default="", help="Version filter (e.g. 4.18)")
    args = parser.parse_args()

    data = json.load(sys.stdin)

    if args.command == "tags":
        out = filter_tags(data, args.tag)
    else:
        out = filter_images(data, args.tag)

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
