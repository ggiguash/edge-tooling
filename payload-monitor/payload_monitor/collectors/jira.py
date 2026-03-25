"""Search JIRA for existing bugs related to edge topology failures."""

import logging
import os
import urllib.parse
from typing import Optional

import requests

from ..config import Config
from ..models import JiraBug, JobRun, SuggestedBug

logger = logging.getLogger(__name__)

JIRA_BASE = "https://issues.redhat.com"
SEARCH_URL = f"{JIRA_BASE}/rest/api/2/search"


def _get_auth() -> Optional[tuple[str, str]]:
    """Get JIRA auth from environment variables."""
    token = os.environ.get("JIRA_TOKEN")
    if token:
        return None  # Use bearer token instead
    return None


def _get_headers() -> dict:
    """Get request headers with auth if available."""
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("JIRA_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _has_auth() -> bool:
    return bool(os.environ.get("JIRA_TOKEN"))


def search_bugs(
    job_name: str,
    config: Config,
    max_results: int = 5,
) -> list[JiraBug]:
    """Search JIRA for bugs matching a failing job name."""
    if not _has_auth():
        logger.debug("JIRA_TOKEN not set, skipping JIRA search")
        return []

    # Search by job name in summary or description
    # Escape special JQL characters
    escaped = job_name.replace('"', '\\"')
    jql = (
        f'project = {config.jira.project} '
        f'AND (summary ~ "{escaped}" OR description ~ "{escaped}") '
        f'AND status not in (Closed, "Release Pending") '
        f'ORDER BY updated DESC'
    )

    try:
        resp = requests.get(
            SEARCH_URL,
            params={"jql": jql, "maxResults": max_results, "fields": "summary,status,assignee,priority,components"},
            headers=_get_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"JIRA search failed for {job_name}: {e}")
        return []

    bugs = []
    for issue in data.get("issues", []):
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        status = fields.get("status") or {}
        priority = fields.get("priority") or {}
        components = fields.get("components", [])

        bugs.append(JiraBug(
            key=issue["key"],
            summary=fields.get("summary", ""),
            status=status.get("name", ""),
            assignee=assignee.get("displayName", "Unassigned"),
            priority=priority.get("name", ""),
            url=f"{JIRA_BASE}/browse/{issue['key']}",
            component=components[0].get("name", "") if components else "",
        ))

    return bugs


def search_bugs_for_jobs(
    failing_jobs: list[JobRun],
    config: Config,
) -> dict[str, list[JiraBug]]:
    """Search JIRA for bugs matching each failing job.

    Returns a dict mapping job name -> list of matching bugs.
    """
    if not _has_auth():
        logger.info("JIRA_TOKEN not set — JIRA bug matching disabled")
        return {}

    results = {}
    for job in failing_jobs:
        bugs = search_bugs(job.name, config)
        if bugs:
            logger.info(f"  Found {len(bugs)} JIRA bugs for {job.name}")
            results[job.name] = bugs

    return results


def create_bug_url(
    title: str,
    description: str,
    config: Config,
) -> str:
    """Generate a JIRA create-issue URL with pre-populated fields."""
    params = {
        "project.key": config.jira.project,
        "issuetype": "Bug",
        "summary": title,
        "description": description,
    }
    return f"{JIRA_BASE}/secure/CreateIssue!default.jspa?{urllib.parse.urlencode(params)}"


def suggest_bug(
    job: JobRun,
    version: str,
    config: Config,
) -> SuggestedBug:
    """Generate a suggested JIRA bug for an unmatched failing job."""
    failing_test_names = [t.name for t in job.failing_tests[:5]]

    title = f"[{job.topology}] {job.name} failing in {version} nightly"

    description_lines = [
        f"*Job*: [{job.name}|{job.prow_url}]",
        f"*Topology*: {job.topology}",
        f"*Version*: {version}",
        f"*Job Type*: {job.job_type.value}",
        "",
        "*Failing Tests*:",
    ]
    for t in job.failing_tests[:5]:
        description_lines.append(f"- {t.name}")
        if t.error_message:
            # Truncate error for JIRA
            err = t.error_message[:200].replace("\n", " ")
            description_lines.append(f"  {{noformat}}{err}{{noformat}}")

    if job.error_summary:
        description_lines.extend(["", f"*Error Summary*: {job.error_summary}"])

    description = "\n".join(description_lines)

    return SuggestedBug(
        title=title,
        description=description,
        job_name=job.name,
        topology=job.topology or "",
        version=version,
        failing_tests=failing_test_names,
        create_url=create_bug_url(title, description, config),
    )
