"""Fetch test and job health data from Sippy."""

import logging
from typing import Optional

import requests

from ..config import Config
from ..models import Regression

logger = logging.getLogger(__name__)

BASE_URL = "https://sippy.dptools.openshift.org"
JOBS_URL = f"{BASE_URL}/api/jobs"
TESTS_URL = f"{BASE_URL}/api/tests"


def _sippy_release(version: str) -> str:
    """Convert version string to Sippy release format (e.g., '4.19')."""
    return version


def _is_edge_job(name: str, config: Config) -> Optional[str]:
    """Check if a job name matches any edge topology, return topology name."""
    for topo in config.topologies:
        if topo.matches(name):
            return topo.name
    return None


def fetch_edge_jobs(release: str, config: Config) -> list[dict]:
    """Fetch jobs from Sippy and filter for edge topologies."""
    sippy_release = _sippy_release(release)
    logger.info(f"Fetching Sippy jobs for release {sippy_release}")

    try:
        resp = requests.get(JOBS_URL, params={"release": sippy_release}, timeout=30)
        resp.raise_for_status()
        all_jobs = resp.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Sippy jobs for {sippy_release}: {e}")
        return []

    if not isinstance(all_jobs, list):
        logger.error(f"Unexpected Sippy jobs response format: {type(all_jobs)}")
        return []

    edge_jobs = []
    for job in all_jobs:
        name = job.get("name", "")
        topology = _is_edge_job(name, config)
        if topology:
            job["_topology"] = topology
            edge_jobs.append(job)

    logger.info(f"  Found {len(edge_jobs)} edge jobs for {sippy_release}")
    return edge_jobs


def fetch_edge_tests(release: str, config: Config) -> list[dict]:
    """Fetch tests from Sippy — used for additional regression detection."""
    sippy_release = _sippy_release(release)
    logger.debug(f"Fetching Sippy tests for release {sippy_release}")

    try:
        resp = requests.get(TESTS_URL, params={"release": sippy_release}, timeout=60)
        resp.raise_for_status()
        return resp.json() if isinstance(resp.json(), list) else []
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Sippy tests for {sippy_release}: {e}")
        return []


def identify_regressions(
    edge_jobs: list[dict],
    pass_rate_threshold: float = 80.0,
    min_runs: int = 3,
) -> list[Regression]:
    """Identify jobs with significant pass rate drops as regressions.

    Jobs with fewer than min_runs are excluded (insufficient data to confirm regression).
    """
    regressions = []

    for job in edge_jobs:
        current_pass = job.get("current_pass_percentage", 0)
        previous_pass = job.get("previous_pass_percentage", 0)
        current_runs = job.get("current_runs", 0)
        name = job.get("name", "")
        topology = job.get("_topology", "")
        jira_component = job.get("jira_component", "")
        triage_url = f"{BASE_URL}/sippy-ng/jobs/{name}"

        # Skip jobs with too few runs — insufficient data to confirm regression
        if current_runs < min_runs:
            continue

        # Flag as regression if pass rate dropped significantly or is below threshold
        is_regression = False
        if previous_pass > 0 and (previous_pass - current_pass) > 10:
            is_regression = True
        if current_pass < pass_rate_threshold and current_runs >= 5:
            is_regression = True

        if is_regression:
            regressions.append(Regression(
                test_name=name,
                test_id=str(job.get("id", "")),
                component=jira_component,
                capability="",
                basis_pass_rate=previous_pass,
                sample_pass_rate=current_pass,
                topology=topology,
                triage_url=triage_url,
                current_runs=current_runs,
            ))

    return regressions


def collect(config: Config, versions: list[str]) -> dict[str, list[Regression]]:
    """Collect Sippy regressions for all configured versions.

    Returns a dict mapping version -> list of regressions.
    """
    results = {}
    for version in versions:
        edge_jobs = fetch_edge_jobs(version, config)
        regressions = identify_regressions(edge_jobs)
        if regressions:
            logger.info(
                f"  {version}: {len(regressions)} edge job regressions detected"
            )
        results[version] = regressions
    return results
