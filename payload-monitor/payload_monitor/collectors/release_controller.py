"""Fetch nightly payload data from the amd64 release controller."""

import logging
from typing import Optional

import requests

from ..config import Config
from ..models import (
    JobResult,
    JobRun,
    JobType,
    Payload,
    PayloadStatus,
    StreamReport,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://amd64.ocp.releases.ci.openshift.org"
TAGS_URL = f"{BASE_URL}/api/v1/releasestream/{{stream}}/tags"
RELEASE_URL = f"{BASE_URL}/api/v1/releasestream/{{stream}}/release/{{tag}}"
SIPPY_RELEASES_URL = "https://sippy.dptools.openshift.org/api/releases"
STREAMS_URL = f"{BASE_URL}/api/v1/releasestreams/accepted"

# Fallback versions if auto-discovery fails
FALLBACK_VERSIONS = ["4.18", "4.19", "4.20", "4.21", "4.22", "4.23", "5.0"]

# Only monitor versions >= this threshold
MIN_VERSION = (4, 18)


def _stream_name(version: str) -> str:
    return f"{version}.0-0.nightly"


def _parse_job_result(state: str) -> JobResult:
    state_lower = state.lower()
    if state_lower == "succeeded":
        return JobResult.SUCCESS
    if state_lower == "failed":
        return JobResult.FAILURE
    if state_lower in ("pending", "triggered"):
        return JobResult.PENDING
    return JobResult.UNKNOWN


def _parse_phase(phase: str) -> PayloadStatus:
    phase_lower = phase.lower()
    if phase_lower == "accepted":
        return PayloadStatus.ACCEPTED
    if phase_lower == "rejected":
        return PayloadStatus.REJECTED
    return PayloadStatus.PENDING


def _classify_topology(job_name: str, config: Config) -> Optional[str]:
    for topo in config.topologies:
        if topo.matches(job_name):
            return topo.name
    return None


def _parse_jobs(
    jobs_dict: dict, job_type: JobType, config: Config
) -> list[JobRun]:
    runs = []
    for name, info in jobs_dict.items():
        topology = _classify_topology(name, config)
        runs.append(JobRun(
            name=name,
            url=info.get("url", ""),
            result=_parse_job_result(info.get("state", "")),
            job_type=job_type,
            topology=topology,
            prow_url=info.get("url", ""),
        ))
    return runs


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    """Parse '4.18' into (4, 18) for comparison."""
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return (0,)


def _discover_from_sippy() -> list[str]:
    """Discover versions from the Sippy releases API."""
    try:
        resp = requests.get(SIPPY_RELEASES_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        releases = data.get("releases", [])
    except requests.RequestException as e:
        logger.warning(f"Sippy discovery failed: {e}")
        return []

    versions = []
    for r in releases:
        if "-" in r or not r[0].isdigit():
            continue
        if _parse_version_tuple(r) >= MIN_VERSION:
            versions.append(r)
    return versions


def _discover_from_release_controller() -> list[str]:
    """Discover versions from the release controller's nightly streams."""
    try:
        resp = requests.get(STREAMS_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning(f"Release controller discovery failed: {e}")
        return []

    versions = []
    for stream_name in data.keys():
        if not stream_name.endswith(".0-0.nightly"):
            continue
        version = stream_name.replace(".0-0.nightly", "")
        if _parse_version_tuple(version) >= MIN_VERSION:
            versions.append(version)
    return versions


def _auto_discover_versions() -> list[str]:
    """Auto-discover active OCP versions from Sippy and the release controller.

    Queries both sources and merges results to ensure all active nightly
    streams are found (Sippy may lag behind the release controller for
    newer versions like 4.23 and 5.0).
    """
    sippy_versions = _discover_from_sippy()
    rc_versions = _discover_from_release_controller()

    # Merge and deduplicate
    all_versions = list(set(sippy_versions + rc_versions))

    if not all_versions:
        logger.warning("No versions found via auto-discovery, using fallback")
        return FALLBACK_VERSIONS

    all_versions.sort(key=_parse_version_tuple)
    logger.info(f"Auto-discovered versions: {all_versions}")
    return all_versions


def discover_streams(config: Config) -> list[str]:
    """Return list of nightly stream names to monitor."""
    if config.versions.override:
        return [_stream_name(v) for v in config.versions.override]
    if config.versions.auto_discover:
        versions = _auto_discover_versions()
        return [_stream_name(v) for v in versions]
    return [_stream_name(v) for v in FALLBACK_VERSIONS]


def fetch_tags(stream: str, limit: int = 5) -> list[dict]:
    """Fetch recent payload tags for a stream.

    Only returns Accepted or Rejected payloads (skips Ready/Pending).
    Fetches extra tags to ensure we get enough terminal payloads.
    """
    url = TAGS_URL.format(stream=stream)
    logger.info(f"Fetching tags from {url}")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch tags for {stream}: {e}")
        return []

    terminal = []
    for tag in data.get("tags", []):
        phase = tag.get("phase", "").lower()
        if phase in ("accepted", "rejected"):
            terminal.append(tag)
            if len(terminal) >= limit:
                break
    return terminal


def fetch_release_detail(stream: str, tag: str) -> Optional[dict]:
    """Fetch detailed job results for a specific release tag."""
    url = RELEASE_URL.format(stream=stream, tag=tag)
    logger.debug(f"Fetching release detail from {url}")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch detail for {tag}: {e}")
        return None


def fetch_payload(stream: str, tag_data: dict, config: Config) -> Payload:
    """Fetch full payload data including job results."""
    tag = tag_data["name"]
    version = stream.split(".0-0.nightly")[0]

    detail = fetch_release_detail(stream, tag)
    jobs = []
    if detail and "results" in detail:
        results = detail["results"]
        blocking = results.get("blockingJobs", {})
        informing = results.get("informingJobs", {})
        jobs.extend(_parse_jobs(blocking, JobType.BLOCKING, config))
        jobs.extend(_parse_jobs(informing, JobType.INFORMING, config))

    release_url = f"{BASE_URL}/releasestream/{stream}/release/{tag}"

    return Payload(
        tag=tag,
        stream=stream,
        version=version,
        status=_parse_phase(tag_data.get("phase", "")),
        phase=tag_data.get("phase", ""),
        url=release_url,
        jobs=jobs,
    )


def collect(config: Config) -> list[StreamReport]:
    """Collect payload data for all configured streams."""
    streams = discover_streams(config)
    reports = []

    for stream in streams:
        version = stream.split(".0-0.nightly")[0]
        logger.info(f"Collecting payloads for {stream}")
        tags = fetch_tags(stream, limit=config.payloads_per_stream)

        payloads = []
        for tag_data in tags:
            payload = fetch_payload(stream, tag_data, config)
            edge_jobs = payload.edge_jobs
            if edge_jobs:
                failing = [j for j in edge_jobs if j.result == JobResult.FAILURE]
                logger.info(
                    f"  {payload.tag}: {payload.phase} — "
                    f"{len(edge_jobs)} edge jobs, {len(failing)} failing"
                )
            payloads.append(payload)

        reports.append(StreamReport(
            stream=stream,
            version=version,
            payloads=payloads,
        ))

    return reports
