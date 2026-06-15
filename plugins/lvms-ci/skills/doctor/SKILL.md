---
name: lvms-ci:doctor
argument-hint: [release1,release2,...]
description: Analyze CI for LVMS periodic jobs and produce an HTML summary
user-invocable: true
allowed-tools: Skill, Bash, Read, Write, Glob, Grep, Workflow
---

# lvms-ci:doctor

## Synopsis

```bash
/lvms-ci:doctor main
/lvms-ci:doctor 4.20,4.21,4.22,main
```

## Description

Accepts a comma-separated list of release versions (or `main`), runs analysis for each release, and produces a single HTML summary file consolidating all results. Uses deterministic scripts for data collection, artifact download, aggregation, and HTML generation. LLM agents are used only for per-job root cause analysis.

## Arguments

- `<ARGUMENTS>` (required): Comma-separated list of release versions (e.g., `main` or `4.20,4.21,4.22,main`)

## Work Directory

Compute once at the start by running `date +%y%m%d` and substituting into the path below. In all commands, replace `<WORKDIR>` with the computed path — do not use shell variables.

```text
/tmp/lvm-operator-ci-claude-workdir.<YYMMDD>
```

## Implementation Steps

### Step 0: Verify Workflow Tool Availability

**CRITICAL — hard requirement**: This skill requires the `Workflow` tool. Before proceeding, confirm that `Workflow` is listed in your available tools. If it is NOT available, STOP IMMEDIATELY and report this error to the user:

```text
ERROR: The Workflow tool is not available in this Claude Code version.
The lvms-ci:doctor skill requires Workflow support (Claude Code 2.2+).
Please upgrade Claude Code and retry.
```

Do NOT attempt to work around the missing tool by spawning individual agents, using sequential analysis, or any other fallback. The skill cannot produce correct results without deterministic workflow orchestration.

### Step 1: Prepare — Collect and Download All Artifacts

**Goal**: Deterministically collect all failed jobs and download their artifacts before any LLM analysis.

**Actions**:

1. Determine today's `<WORKDIR>` by running `date +%y%m%d` and substituting into `/tmp/lvm-operator-ci-claude-workdir.<YYMMDD>`. Use this value in all subsequent commands.
2. Run the prepare script:

   ```text
   bash plugins/lvms-ci/scripts/doctor.sh prepare --component lvm-operator --workdir <WORKDIR> <ARGUMENTS>
   ```

3. The script deterministically:
   - For each release: fetches failed periodic jobs, downloads artifacts, writes `<WORKDIR>/jobs/release-<version>-jobs.json`
   - Outputs a JSON summary listing all releases, job counts, and file paths
4. Read the JSON output to know which releases have jobs to analyze and how many

**Job JSON field names** (use these exactly — do NOT guess alternatives like `job_name`):

- `job` — full job name
- `build_id` — unique build identifier
- `artifacts_dir` — local path to downloaded artifacts
- `url` — Prow job URL
- `status` — job result (`failure`, `FAILURE`, `SUCCESS`, `PENDING`)

**Error Handling**:

- If `<ARGUMENTS>` is empty, show usage and stop
- If a release has no failed jobs, its jobs JSON will be an empty array — skip analysis for that release
- If a release has an `"error"` field in the JSON summary, data collection failed for that release — report the error to the user but continue with other releases

### Step 2: Analyze via Workflow

**Goal**: Run per-job analysis in parallel, orchestrated deterministically by a workflow script.

**Actions**:

1. Read `<WORKDIR>/workflows/analyze-jobs.json` (written by the prepare script in Step 1). If the array is empty, skip to Step 3.
2. Invoke the Workflow tool:

   ```text
   Workflow(
     scriptPath: "plugins/lvms-ci/scripts/doctor-analyze.js",
     args: {
       jobs: <contents of analyze-jobs.json>,
       prow_job_skill: "/lvms-ci:prow-job"
     }
   )
   ```

3. The workflow runs in the background and sends a completion notification when done. Wait for the notification, then proceed to Step 3. Do NOT stop or end your turn between Step 2 and Step 3.

**CRITICAL — no fallback**: If the Workflow tool call fails for any reason (script error, timeout, API error), STOP and report the error to the user. Do NOT fall back to sequential Agent-based spawning — sequential execution risks hitting the turn timeout.

The workflow runs all job analyses in parallel — each agent runs the prow-job skill and saves the report.

**Error Handling**:

- If individual analysis agents fail, the workflow continues with the remaining jobs
- The workflow returns `{analyzed, failed, total}` — use these for the summary

### Step 3: Finalize — Aggregate and Generate HTML Report

**IMPORTANT**: This step is MANDATORY. The task is incomplete without it. You MUST run this even if previous steps produced errors.

**Goal**: Deterministically aggregate results and generate the HTML report.

**Actions**:

1. Run the finalize script:

   ```text
   bash plugins/lvms-ci/scripts/doctor.sh finalize --component lvm-operator --workdir <WORKDIR> <ARGUMENTS>
   ```

2. The script deterministically:
   - Runs `aggregate.py` for each release → `summary.json` files
   - Runs `create-report.py` → `report-lvm-operator-ci-doctor.html`
3. Report the script's output to the user

### Step 4: Report Completion

**Actions**:

1. Display the path to the generated HTML file
2. Summarize: failed job counts per release

**Example Output**:

```text
Summary:
  Periodics:
    Release main: 3 failed periodic jobs
    Release 4.22: 0 failed periodic jobs

HTML report generated: <WORKDIR>/report-lvm-operator-ci-doctor.html
```

## Examples

### Example 1: Analyze Main Branch Only

```bash
/lvms-ci:doctor main
```

### Example 2: Analyze Multiple Releases

```bash
/lvms-ci:doctor 4.20,4.21,4.22,main
```

## Prerequisites

- `gsutil` CLI must be installed for GCS access (uses anonymous access on public buckets)
- Internet access to fetch job data from Prow/GCS
- Bash shell, Python 3

## Related Skills

- **lvms-ci:prow-job**: Single job analysis (used by Step 2 workflow agents)

## Notes

- **Deterministic scripts** handle: data collection, artifact download, aggregation, HTML generation
- **LLM agents** handle: per-job root cause analysis (via Step 2 workflow)
- Step 2 uses a Workflow script (`doctor-analyze.js`) that guarantees parallel agent execution via `parallel()`
- The `prepare` script downloads all artifacts upfront so prow-job agents use local paths (no redundant downloads)
- The `finalize` script runs aggregation and HTML generation in one call
- All intermediate files use prescribed filenames in `<WORKDIR>` — no improvised names
- The HTML report is self-contained (no external CSS/JS dependencies)
- If a release analysis fails, it is noted in the report but does not block other releases
