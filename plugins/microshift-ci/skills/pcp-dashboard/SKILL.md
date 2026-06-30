---
name: microshift-ci:pcp-dashboard
argument-hint: <workdir-or-prow-url>
description: Generate interactive PCP performance dashboard from per-VM CI artifacts
user-invocable: true
allowed-tools: Bash, Read, Write, WebFetch
---

# microshift-ci:pcp-dashboard

## Synopsis

```bash
/microshift-ci:pcp-dashboard <workdir-or-prow-url>
```

## Description

Generates a self-contained interactive HTML dashboard showing PCP (Performance Co-Pilot) metrics for each test scenario's VM. Produces CPU, memory, disk I/O, and disk usage charts organized per scenario with a navigable sidebar.

Each MicroShift CI scenario runs on its own VM that collects PCP archives at `scenario-info/<scenario>/vms/host1/pcp/pcp-archives.tar`. This skill extracts those archives, parses the metrics, and produces an interactive dashboard using Chart.js — no external dependencies at runtime.

## Arguments

- `<ARGUMENTS>` (required): One of:
  - **Workdir path**: Path to an existing work directory with downloaded artifacts (e.g., `/tmp/microshift-ci-claude-workdir.260629`)
  - **Prow job URL**: Full Prow job URL — artifacts will be downloaded first

## Implementation Steps

### Step 1: Determine Input Type and Prepare Workdir

**Goal**: Detect whether the argument is a local path or a Prow URL, and ensure artifacts are available locally.

**Actions**:

1. If the argument starts with `https://` or `http://`:
   - Parse the Prow URL to extract the GCS path:
     - `https://prow.ci.openshift.org/view/gs/<path>` → `gs://<path>`
     - `https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/<path>` → `gs://<path>`
   - Extract the build ID (last path segment) and job name
   - Compute the workdir: `/tmp/microshift-pcp-dashboard.<BUILD_ID>`
   - Download artifacts:

     ```text
     mkdir -p <WORKDIR>/artifacts
     gsutil -q -m cp -r gs://<path>/ <WORKDIR>/artifacts/
     ```

2. If the argument is a local path:
   - Verify the directory exists and contains an `artifacts/` subdirectory
   - Use it directly as `<WORKDIR>`

### Step 2: Validate Prerequisites

**Goal**: Ensure required tools are available.

**Actions**:

1. Check that `pcp2json` is available:

   ```text
   command -v pcp2json
   ```

   If missing, report: `Install with: sudo dnf install -y pcp-export-pcp2json`

2. Check that Python 3 is available

### Step 3: Generate Dashboard

**Goal**: Run the dashboard generation pipeline.

**Actions**:

1. Run the dashboard generator:

   ```text
   bash plugins/microshift-ci/scripts/pcp-graphs/generate-dashboard.sh --workdir <WORKDIR>
   ```

2. The script:
   - Finds all per-VM PCP tarballs (`pcp-archives.tar`) in scenario artifact directories
   - Extracts each tarball and runs PCP metric extraction (CPU, memory, disk I/O, disk usage)
   - Collects scenario metadata from junit.xml files
   - Assembles a self-contained HTML dashboard at `<WORKDIR>/pcp-dashboard.html`

3. Report the output path to the user

### Step 4: Open Dashboard

**Goal**: Make the dashboard easily accessible.

**Actions**:

1. Report the full path to the generated HTML file
2. Attempt to open it in the default browser:

   ```text
   open <WORKDIR>/pcp-dashboard.html
   ```

**Error Handling**:

- If no PCP tarballs are found, report that no per-VM PCP data is available for this job
- If `pcp2json` is not installed, the script automatically falls back to running it in a container via podman or docker. If neither is available, it reports installation options and stops
- If individual scenario extraction fails, skip that scenario and continue with others

## Examples

### Example 1: From an existing doctor workdir

```bash
/microshift-ci:pcp-dashboard /tmp/microshift-ci-claude-workdir.260629
```

### Example 2: From a Prow job URL

```bash
/microshift-ci:pcp-dashboard https://prow.ci.openshift.org/view/gs/test-platform-results/logs/periodic-ci-openshift-microshift-main-e2e-aws-tests-bootc-upstream-periodic/2070356586173304832
```

## Prerequisites

- **One of** (for reading PCP archives):
  - `pcp-export-pcp2json` package (native — `dnf install pcp-export-pcp2json`)
  - `podman` or `docker` (container fallback — auto-builds a `pcp2json-tool` image on first use)
- Python 3 (stdlib only — no pip packages required for the dashboard)
- `gsutil` CLI (only required when using Prow URL input)

## Output

Self-contained HTML file at `<WORKDIR>/pcp-dashboard.html` with:

- Sidebar listing all scenarios grouped by build ID, with pass/fail indicators
- Per-scenario interactive charts (zoom, hover tooltips):
  - **CPU Usage**: Stacked area (User, System, I/O Wait)
  - **Memory Usage**: Stacked area (Used, Cached) with Total line
  - **Disk I/O**: Dual Y-axis (Read/Write OPS, Await ms)
  - **Disk Usage**: Per-partition line chart (fill %)
- Summary statistics (peak values) below each chart
- No external dependencies — works offline after generation
