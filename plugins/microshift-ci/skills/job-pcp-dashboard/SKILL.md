---
name: microshift-ci:job-pcp-dashboard
argument-hint: <prow-job-url>
description: Generate interactive PCP performance dashboard from a Prow job URL
user-invocable: true
allowed-tools: Bash, Read
---

# microshift-ci:job-pcp-dashboard

Generate an interactive HTML dashboard with per-VM PCP metrics (CPU, memory, disk I/O, disk usage) from a MicroShift CI job.

## Steps

1. Run the dashboard generator:

   ```bash
   bash plugins/microshift-ci/scripts/pcp-graphs/generate-dashboard.sh --url <ARGUMENTS>
   ```

2. Open the generated dashboard in the default browser. Use `open` on macOS or `xdg-open` on Linux:

   ```bash
   open /tmp/microshift-job-pcp-dashboard.<BUILD_ID>/pcp-dashboard.html
   ```

   The `<BUILD_ID>` is the last segment of the Prow job URL.

## Prerequisites

- `gsutil` CLI (for downloading artifacts from GCS)
- Python 3
- One of: `pcp-export-pcp2json` (native) or `podman` (container fallback)
