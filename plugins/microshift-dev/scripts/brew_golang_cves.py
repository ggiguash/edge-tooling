#!/usr/bin/env python3
"""Golang CVE tracker for MicroShift Brew builds.

Finds the latest nightly MicroShift RPM build in Brew for a given X.Y version,
discovers which Go toolchain was used to build it, and lists CVEs fixed in that
Go version.

Usage: brew_golang_cves.py <version>   (e.g., 4.18 or 4.22)
"""

import argparse
import json
import logging
import re
import ssl
import sys
import xmlrpc.client
from datetime import datetime
from html import unescape

import requests
import urllib3

from lib import brew

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BREWWEB_URL = "https://brewweb.engineering.redhat.com/brew"


def _brew_server():
    """Create a Brew/Koji XML-RPC client."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return xmlrpc.client.ServerProxy(
        BREWHUB_URL, context=ctx, allow_none=True,
    )


def find_latest_nightly_build(server, version):
    """Find the latest MicroShift nightly build in Brew for a given X.Y version.

    Args:
        server: Koji XML-RPC client.
        version: Minor version, e.g., "4.18".

    Returns:
        dict: Build info dict from Koji, or None.

    Raises:
        RuntimeError: On XML-RPC communication failure.
    """
    pattern = f"microshift-{version}*nightly*"
    try:
        results = server.search(pattern, "build", "glob", {"order": "-id", "limit": 1})
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Brew XML-RPC error searching for '{pattern}': {e}") from e
    if not results:
        return None

    try:
        build = server.getBuild(results[0]["id"])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Brew XML-RPC error fetching build {results[0]['id']}: {e}") from e
    return build


def get_buildarch_task_id(server, build, arch="x86_64"):
    """Find the buildArch child task for a given architecture.

    Args:
        server: Koji XML-RPC client.
        build: Build info dict.
        arch: Target architecture.

    Returns:
        int: Task ID of the buildArch task, or None.
    """
    task_id = build.get("task_id")
    if not task_id:
        return None

    try:
        children = server.getTaskChildren(task_id)
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Brew XML-RPC error fetching task children for {task_id}: {e}") from e
    for child in children:
        if child.get("method") == "buildArch" and child.get("arch") == arch:
            return child["id"]
    return None


def fetch_installed_pkgs(task_id):
    """Download installed_pkgs.log from a Brew buildArch task.

    Args:
        task_id: Brew task ID.

    Returns:
        str: Contents of installed_pkgs.log.
    """
    url = f"{BREWWEB_URL}/getfile?taskID={task_id}&name=installed_pkgs.log"
    resp = requests.get(url, verify=False, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_golang_from_installed_pkgs(pkgs_text):
    """Extract the golang version from installed_pkgs.log.

    Args:
        pkgs_text: Contents of installed_pkgs.log.

    Returns:
        dict: {"name": "golang", "nvr": "golang-1.22.12-11.el9", "version": "1.22.12",
               "release": "11.el9"} or None.
    """
    # Format: golang-1.22.12-11.el9.x86_64 <timestamp> <size> <checksum> installed
    pattern = re.compile(
        r"^(golang)-(\d+\.\d+\.\d+)-(\S+)\.(x86_64|aarch64|noarch)\s",
        re.MULTILINE,
    )
    match = pattern.search(pkgs_text)
    if not match:
        return None

    name = match.group(1)
    version = match.group(2)
    release = match.group(3)
    return {
        "name": name,
        "nvr": f"{name}-{version}-{release}",
        "version": version,
        "release": release,
    }


def find_golang_build(server, golang_nvr):
    """Find the Brew build for a golang NVR.

    Args:
        server: Koji XML-RPC client.
        golang_nvr: e.g., "golang-1.22.12-11.el9".

    Returns:
        dict: Build info dict from Koji, or None.
    """
    try:
        results = server.search(golang_nvr, "build", "glob", {"order": "-id", "limit": 1})
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Brew XML-RPC error searching for '{golang_nvr}': {e}") from e
    if not results:
        return None
    try:
        return server.getBuild(results[0]["id"])
    except (xmlrpc.client.Fault, xmlrpc.client.ProtocolError, ConnectionError, OSError) as e:
        raise RuntimeError(f"Brew XML-RPC error fetching build {results[0]['id']}: {e}") from e


def fetch_golang_changelog(build_id):
    """Fetch the changelog from the Brew build page for a golang build.

    Args:
        build_id: Brew build ID.

    Returns:
        str: Raw changelog text, or None if changelog element not found.
    """
    url = f"{BREWWEB_URL}/buildinfo?buildID={build_id}"
    resp = requests.get(url, verify=False, timeout=30)
    resp.raise_for_status()

    match = re.search(r'<td class="changelog">(.*?)</td>', resp.text, re.DOTALL)
    if not match:
        logger.warning("No changelog element found on Brew page for build %s", build_id)
        return None
    return unescape(match.group(1))


def extract_cves_from_changelog(changelog_text):
    """Parse changelog text and extract CVE entries with dates.

    Args:
        changelog_text: Raw changelog text from Brew.

    Returns:
        list[dict]: Each dict has keys: cve, date, author, release, description.
    """
    cves = []
    lines = changelog_text.splitlines()

    current_date = ""
    current_author = ""
    current_release = ""

    # Changelog header pattern: * Mon Jan 01 2026 Author <email> - version-release
    header_re = re.compile(
        r"^\*\s+\w+\s+(\w+\s+\d+\s+\d{4})\s+(.*?)\s+-\s+(.*)$"
    )
    cve_re = re.compile(r"(CVE-\d{4}-\d+)")

    for line in lines:
        header = header_re.match(line.strip())
        if header:
            current_date = header.group(1)
            current_author = header.group(2)
            current_release = header.group(3)
            continue

        cve_matches = cve_re.findall(line)
        if cve_matches:
            for cve_id in cve_matches:
                cves.append({
                    "cve": cve_id,
                    "date": current_date,
                    "author": current_author,
                    "release": current_release,
                    "description": line.strip().lstrip("- "),
                })

    return cves


def format_text(data, verbose=False):
    """Format the output as human-readable text.

    Args:
        data: Output dict from the evaluation.
        verbose: If True, show extra detail.

    Returns:
        str: Formatted text.
    """
    lines = []

    if data.get("error"):
        lines.append(f"ERROR: {data['error']}")
        return "\n".join(lines)

    ms = data.get("microshift_build", {})
    go = data.get("golang", {})
    cves = data.get("cves", [])

    lines.append(f"MicroShift build : {ms.get('nvr', 'N/A')}")
    lines.append(f"Golang version   : {go.get('nvr', 'N/A')}")
    lines.append(f"CVEs fixed       : {len(cves)}")
    lines.append("")

    if cves:
        # Column-aligned output
        date_width = max(len(c["date"]) for c in cves) if cves else 12
        cve_width = max(len(c["cve"]) for c in cves) if cves else 16
        lines.append(f"{'DATE':<{date_width}}  {'CVE':<{cve_width}}  DESCRIPTION")
        lines.append(f"{'-' * date_width}  {'-' * cve_width}  {'-' * 40}")
        for c in cves:
            desc = c["description"] if verbose else ""
            line = f"{c['date']:<{date_width}}  {c['cve']:<{cve_width}}"
            if desc:
                line += f"  {desc}"
            lines.append(line)
    else:
        lines.append("No CVEs found in changelog.")

    return "\n".join(lines)


def _exit_with_error(message, version, json_output, **extra):
    """Print an error in the chosen format and exit.

    Args:
        message: Human-readable error string.
        version: The MicroShift version being queried.
        json_output: If True, print JSON; otherwise formatted text.
        **extra: Additional keys merged into the output dict
                 (e.g., microshift_build, golang).
    """
    error_data = {
        "command": "brew_golang_cves",
        "version": version,
        **extra,
        "error": message,
        "timestamp": datetime.now().isoformat(),
    }
    if json_output:
        print(json.dumps(error_data, indent=2))
    else:
        print(format_text(error_data))
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Find golang CVEs in the latest MicroShift nightly Brew build",
    )
    parser.add_argument("version", help="Minor version, e.g., 4.18 or 4.22")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Output raw JSON instead of formatted text")
    parser.add_argument("--verbose", action="store_true",
                        help="Show CVE description text")
    parser.add_argument("--arch", default="x86_64",
                        help="Build architecture (default: x86_64)")
    args = parser.parse_args()

    version = args.version

    def fail(message, **extra):
        """Shorthand for _exit_with_error bound to this invocation's args."""
        _exit_with_error(message, version, args.json_output, **extra)

    # Step 0: VPN check
    if not brew.check_vpn():
        fail("VPN not connected. Brew requires VPN access.")

    server = _brew_server()

    # Step 1: Find the latest nightly MicroShift build
    logger.info("Searching for latest MicroShift nightly build for %s...", version)
    try:
        ms_build = find_latest_nightly_build(server, version)
    except RuntimeError as e:
        fail(str(e))
    if not ms_build:
        fail(f"No MicroShift nightly build found for {version}")

    logger.info("Found build: %s", ms_build["nvr"])

    # Step 2: Get installed_pkgs.log to find golang version
    logger.info("Fetching installed_pkgs.log...")
    try:
        task_id = get_buildarch_task_id(server, ms_build, arch=args.arch)
    except RuntimeError as e:
        fail(str(e))
    if not task_id:
        fail(f"No {args.arch} buildArch task found for {ms_build['nvr']}")

    try:
        pkgs_text = fetch_installed_pkgs(task_id)
    except requests.RequestException as e:
        fail(f"Failed to fetch installed_pkgs.log for task {task_id}: {e}")
    golang_info = parse_golang_from_installed_pkgs(pkgs_text)
    if not golang_info:
        fail(
            "Golang package not found in installed_pkgs.log",
            microshift_build={"nvr": ms_build["nvr"]},
        )

    logger.info("Golang version: %s", golang_info["nvr"])

    # Step 3: Find the golang build in Brew
    logger.info("Looking up golang build in Brew...")
    try:
        golang_build = find_golang_build(server, golang_info["nvr"])
    except RuntimeError as e:
        fail(str(e), microshift_build={"nvr": ms_build["nvr"]}, golang=golang_info)
    if not golang_build:
        fail(
            f"Golang build {golang_info['nvr']} not found in Brew",
            microshift_build={"nvr": ms_build["nvr"]},
            golang=golang_info,
        )

    # Step 4: Fetch changelog and extract CVEs
    logger.info("Fetching golang changelog...")
    try:
        changelog = fetch_golang_changelog(golang_build["id"])
    except requests.RequestException as e:
        fail(
            f"Failed to fetch golang changelog: {e}",
            microshift_build={"nvr": ms_build["nvr"]},
            golang={"nvr": golang_build["nvr"]},
        )
    if changelog is None:
        fail(
            f"Changelog not found on Brew page for golang build {golang_build['id']}; HTML structure may have changed",
            microshift_build={"nvr": ms_build["nvr"]},
            golang={"nvr": golang_build["nvr"]},
        )
    cves = extract_cves_from_changelog(changelog)
    logger.info("Found %d CVEs in changelog", len(cves))

    output = {
        "command": "brew_golang_cves",
        "version": version,
        "microshift_build": {
            "nvr": ms_build["nvr"],
            "build_id": ms_build["id"],
            "task_id": ms_build.get("task_id"),
        },
        "golang": {
            "nvr": golang_build["nvr"],
            "version": golang_build["version"],
            "release": golang_build["release"],
            "build_id": golang_build["id"],
        },
        "cves": cves,
        "cve_count": len(cves),
        "timestamp": datetime.now().isoformat(),
    }

    if args.json_output:
        print(json.dumps(output, indent=2))
    else:
        print(format_text(output, verbose=args.verbose))


if __name__ == "__main__":
    main()
