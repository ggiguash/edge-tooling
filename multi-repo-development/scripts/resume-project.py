#!/usr/bin/env python3
"""Resolve a project and return structured context for /project:resume and /project:close.

Usage: resume-project.py [project-name-or-number]
Output: JSON to stdout (see resolve_project for schema).
"""

import glob
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL_SUGGESTIONS: dict[str, list[str]] = {
    "bug": [
        "/prow-job:analyze-test-failure",
        "/prow-job:analyze-install-failure",
        "/prow-job:extract-must-gather",
        "/feature-dev:feature-dev",
    ],
    "feature": [
        "/feature-dev:feature-dev",
        "/pr-review-toolkit:review-pr",
    ],
    "ci-testing": [
        "/prow-job:analyze-test-failure",
        "/prow-job:analyze-install-failure",
        "/prow-job:analyze-resource",
        "/prow-job:extract-must-gather",
    ],
    "docs": [
        "/feature-dev:feature-dev",
    ],
    "analysis": [
        "/pr-review-toolkit:review-pr",
        "/prow-job:analyze-test-failure",
        "/feature-dev:feature-dev",
    ],
}
DEFAULT_SKILLS = ["/feature-dev:feature-dev"]

ALWAYS_PRESENT = {"CLAUDE.md", "README.md", ".gitignore"}


def parse_frontmatter(path: Path) -> dict[str, str | list[str]]:
    """Extract YAML frontmatter, handling both scalar values and lists."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}

    if not lines or lines[0].strip() != "---":
        return {}

    result: dict[str, str | list[str]] = {}
    current_list_key: str | None = None

    for line in lines[1:]:
        if line.strip() == "---":
            break

        if line.startswith("  - ") and current_list_key:
            val = line.strip().removeprefix("- ")
            if not isinstance(result.get(current_list_key), list):
                result[current_list_key] = []
            result[current_list_key].append(val)
            continue

        current_list_key = None

        if ":" not in line:
            continue

        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if value == "[]":
            result[key] = []
            continue

        if not value:
            result[key] = ""
            current_list_key = key
            continue

        result[key] = value
    else:
        return {}

    return result


def parse_reference_files(text: str) -> list[dict[str, str]]:
    """Parse the Reference Files markdown table into [{filename, description}]."""
    in_section = False
    found_header = False
    skipped_separator = False
    results = []

    for line in text.splitlines():
        if re.match(r"^##\s+Reference Files", line, re.IGNORECASE):
            in_section = True
            continue

        if in_section and not found_header:
            if "|" in line and "File" in line:
                found_header = True
            elif line.startswith("## "):
                break
            continue

        if found_header and not skipped_separator:
            if re.match(r"^\|[-:\s|]+\|\s*$", line):
                skipped_separator = True
            continue

        if skipped_separator:
            if not line.strip() or line.startswith("## "):
                break
            cells = [c.strip() for c in line.split("|")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                filename = cells[0].strip("`")
                description = cells[1]
                results.append({"filename": filename, "description": description})

    return results


def list_project_files(project_dir: Path) -> list[str]:
    """Recursively list files relative to project_dir, sorted."""
    files = []
    for root, dirs, filenames in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in filenames:
            rel = os.path.relpath(os.path.join(root, f), project_dir)
            files.append(rel)
    files.sort()
    return files


def find_unregistered_files(
    all_files: list[str], manifest_files: list[dict[str, str]]
) -> list[str]:
    """Files on disk not in the Reference Files manifest or ALWAYS_PRESENT."""
    known = ALWAYS_PRESENT | {m["filename"] for m in manifest_files}
    return [f for f in all_files if f not in known and not f.startswith(".")]


def extract_checklist(text: str) -> dict:
    """Extract checked/unchecked items with their section headings."""
    current_section = ""
    checked_items = []
    unchecked_items = []

    for line in text.splitlines():
        heading_match = re.match(r"^#{2,3}\s+(.+)", line)
        if heading_match:
            current_section = heading_match.group(1).strip()
            continue

        item_match = re.match(r"^\s*- \[([ xX])\] (.+)$", line)
        if item_match:
            done = item_match.group(1).lower() == "x"
            entry = {"text": item_match.group(2).strip(), "section": current_section}
            if done:
                checked_items.append(entry)
            else:
                unchecked_items.append(entry)

    return {
        "checked": len(checked_items),
        "unchecked": len(unchecked_items),
        "total": len(checked_items) + len(unchecked_items),
        "unchecked_items": unchecked_items,
        "checked_items": checked_items,
    }


def resolve_repo_context(repos: list[str], root: Path) -> list[dict[str, str]]:
    """For each repo, find the best context file (repo CLAUDE.md or preset context)."""
    results = []
    for repo in repos:
        repo_claude = root / "repos" / repo / "CLAUDE.md"
        if repo_claude.is_file():
            results.append({
                "repo": repo,
                "path": str(repo_claude.relative_to(root)),
                "source": "repo",
            })
            continue

        matches = glob.glob(str(root / "presets" / "*" / "context" / f"{repo}.md"))
        if matches:
            results.append({
                "repo": repo,
                "path": str(Path(matches[0]).relative_to(root)),
                "source": "preset",
            })

    return results


def get_recent_names(root: Path) -> list[str]:
    """Get recent non-done project names via recent-projects.py --names."""
    script = root / "scripts" / "recent-projects.py"
    if not script.is_file():
        return _fallback_project_names(root)
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--names"],
            capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
            timeout=5,
        )
        if result.returncode != 0:
            return _fallback_project_names(root)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return _fallback_project_names(root)


def _fallback_project_names(root: Path) -> list[str]:
    """Fallback: list project directories sorted alphabetically."""
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return []
    return sorted(d.name for d in projects_dir.iterdir() if d.is_dir())


def resolve_project(arg: str | None, root: Path) -> dict:
    """Resolve a project argument and return full structured context.

    Returns a dict with:
      status: "ok" | "not_found" | "no_projects" | "out_of_range" | "no_argument"
      error_message: str (when status != "ok")
      alternatives: list[str] (when status != "ok")
      project: dict (only when status == "ok")
    """
    projects_dir = root / "projects"

    if not projects_dir.is_dir():
        return {"status": "no_projects", "error_message": "No projects/ directory found.", "alternatives": []}

    if arg is None:
        names = get_recent_names(root)
        if not names:
            return {"status": "no_projects", "error_message": "No active projects found.", "alternatives": []}
        return {"status": "no_argument", "alternatives": names}

    if arg.isdigit():
        names = get_recent_names(root)
        if not names:
            return {"status": "no_projects", "error_message": "No recent projects found.", "alternatives": []}
        idx = int(arg) - 1
        if idx < 0 or idx >= len(names):
            return {
                "status": "out_of_range",
                "error_message": f"Only {len(names)} projects exist.",
                "alternatives": names,
            }
        project_name = names[idx]
    else:
        project_name = arg

    project_dir = projects_dir / project_name
    if not project_dir.is_dir():
        all_names = sorted(d.name for d in projects_dir.iterdir() if d.is_dir())
        return {
            "status": "not_found",
            "error_message": f"Project '{project_name}' not found.",
            "alternatives": all_names,
        }

    claude_md = project_dir / "CLAUDE.md"
    readme = project_dir / "README.md"

    if claude_md.is_file():
        context_file = str(claude_md.relative_to(root))
        context_type = "claude_md"
        try:
            text = claude_md.read_text()
        except OSError:
            text = ""
    elif readme.is_file():
        context_file = str(readme.relative_to(root))
        context_type = "readme"
        try:
            text = readme.read_text()
        except OSError:
            text = ""
    else:
        context_file = None
        context_type = "none"
        text = ""

    fm = parse_frontmatter(claude_md) if claude_md.is_file() else {}
    has_frontmatter = bool(fm)

    repos_list = fm.get("repos", [])
    if isinstance(repos_list, str):
        repos_list = [repos_list] if repos_list else []

    ref_files = parse_reference_files(text) if text else []
    all_files = list_project_files(project_dir)
    unregistered = find_unregistered_files(all_files, ref_files) if ref_files else []
    checklist = extract_checklist(text) if text else {
        "checked": 0, "unchecked": 0, "total": 0,
        "unchecked_items": [], "checked_items": [],
    }
    repo_context = resolve_repo_context(repos_list, root)

    project_type = fm.get("type", "")
    if isinstance(project_type, list):
        project_type = project_type[0] if project_type else ""
    suggestions = SKILL_SUGGESTIONS.get(project_type, DEFAULT_SKILLS)

    return {
        "status": "ok",
        "project": {
            "name": project_name,
            "dir": str(project_dir.relative_to(root)),
            "context_file": context_file,
            "context_type": context_type,
            "has_frontmatter": has_frontmatter,
            "frontmatter": {
                "project": fm.get("project", ""),
                "type": fm.get("type", ""),
                "created": fm.get("created", ""),
                "status": fm.get("status", ""),
                "jira": fm.get("jira", ""),
                "repos": repos_list,
                "related_links": fm.get("related_links") or [],
            },
            "reference_files": ref_files,
            "has_reference_files": bool(ref_files),
            "all_files": all_files,
            "unregistered_files": unregistered,
            "checklist": checklist,
            "repo_context_files": repo_context,
            "skill_suggestions": suggestions,
        },
    }


def main():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parent.parent))
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    result = resolve_project(arg, root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
