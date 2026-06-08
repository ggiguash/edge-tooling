---
name: microshift-ci:create-bugs
argument-hint: <source1>[,<source2>,...] [--create]
description: Create JIRA bugs from analyze-ci failure reports with cross-release deduplication (dry-run by default)
user-invocable: true
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, mcp__jira__jira_create_issue, mcp__jira__jira_get_issue, mcp__jira__jira_add_comment
---

# microshift-ci:create-bugs

## Synopsis

```bash
/microshift-ci:create-bugs <source> [--create]
/microshift-ci:create-bugs <source1>,<source2>,... [--create]
```

## Description

Reads individual job analysis reports produced by `microshift-ci:doctor` and creates JIRA bugs in USHIFT for CI test failures. Operates in **dry-run mode by default** - it shows what bugs would be created without actually creating them. Use `--create` to perform actual issue creation.

Candidates are always **fuzzy-matched across sources** using token-based Jaccard similarity (50% threshold) with step-name bucketing — the same root cause appearing in multiple releases becomes a single candidate and a single Jira bug referencing all affected releases.

This command does NOT re-analyze CI jobs. It consumes existing job analysis files from `<WORKDIR>`.

## Arguments

- `<ARGUMENTS>` (required): Source identifier(s), optionally followed by flags
  - `<sources>` (required): One or more comma-separated sources. Each source is one of:
    - **Release version** (e.g., `4.22`, `main`): Looks for files matching `analyze-ci-release-<release>-job-*.txt`
    - **PR number** (e.g., `pr-6396` or `pr6396`): Looks for files matching `analyze-ci-prs-job-*-pr<number>-*.txt`
    - **Rebase PR shorthand** (e.g., `rebase-release-4.22`): Resolves to the corresponding rebase PR by scanning existing `analyze-ci-prs-job-*` files for the matching release version in their content
  - `--create` (optional): Actually create/update JIRA issues. Without this flag, only a dry-run report is produced. Auto-decisions (create/update/skip) are pre-computed by `search-bugs.py --merge`.

## Prerequisites

- Job analysis files must already exist in `<WORKDIR>`:
  - For releases: `analyze-ci-release-<release>-job-*.txt` (produced by `/microshift-ci:doctor`)
  - For PRs: `analyze-ci-prs-job-*-pr<number>-*.txt` (produced by `/microshift-ci:doctor`)
- Each job file must contain a `--- STRUCTURED SUMMARY ---` block (see below)
- MCP Jira server must be configured and accessible
- User must have permissions to create issues in USHIFT

### STRUCTURED SUMMARY Block

Each job analysis file produced by `/microshift-ci:prow-job` must end with a machine-readable block:

```text
--- STRUCTURED SUMMARY ---
SEVERITY: <1-5>
STACK_LAYER: <AWS Infra|External Infrastructure|build phase|deploy phase|test setup phase|Test Configuration|test|teardown>
STEP_NAME: <the CI step where the error occurred>
ERROR_SIGNATURE: <concise, unique description of the root cause error>
ROOT_CAUSE: <one-line description of WHY the failure happened — the underlying mechanism, not the surface symptom>
RAW_ERROR: <verbatim primary error message from logs — used for deterministic grouping>
INFRASTRUCTURE_FAILURE: <true|false>
JOB_URL: <full prow job URL>
JOB_NAME: <full periodic job name>
RELEASE: <X.YY>
FINISHED: <job finish date in YYYY-MM-DD format>
--- END STRUCTURED SUMMARY ---
```

If a job file lacks this block, it is skipped with a warning.

## Work Directory

Compute once at the start by running `date +%y%m%d` and substituting into the path below. In all commands, replace `<WORKDIR>` with the computed path — do not use shell variables.

```text
/tmp/microshift-ci-claude-workdir.<YYMMDD>
```

## Implementation Steps

### Step 1: Prepare Bug Candidates (Deterministic Script)

**Actions**:

1. Parse `<ARGUMENTS>` to extract source(s) and detect the `--create` flag
2. Split sources on commas to get `SOURCES` list (e.g., `["4.22"]` or `["4.20", "4.21", "4.22", "5.0", "main"]`)
3. Compute `SOURCE_TAG` — a short identifier used in per-run output filenames (merged candidates, results, report). Use the **first source** in the list (e.g., `4.22`, `main`, `rebase-release-4.22`). Do NOT concatenate all sources.
4. Determine mode: if `--create` is present, set `MODE=create`; otherwise `MODE=dry-run`
5. Determine today's WORKDIR path by running `date +%y%m%d` and substituting into `/tmp/microshift-ci-claude-workdir.<YYMMDD>`. Run `mkdir -p` on it.
6. For **each source** in `SOURCES`, run the preparation script:

   ```text
   python3 plugins/microshift-ci/scripts/search-bugs.py <source> --workdir <WORKDIR>
   ```

   Each invocation writes `<WORKDIR>/analyze-ci-bug-candidates-<source>.json` containing parsed and deduplicated bug candidates with pre-computed `keywords`, `test_ids`, `jobs[]`, and `analysis_text`.

**Error Handling**:

- No arguments: show usage and stop
- Script exits with error if no job files found — relay its error message to the user

### Step 2: Search Jira for Existing Bugs and Write Bug Mapping Files

Run the query script to search JIRA for duplicates, regressions, and open AI-generated bugs. The script reads credentials from `JIRA_URL`, `JIRA_USERNAME`, and `JIRA_API_TOKEN` environment variables.

```text
python3 plugins/microshift-ci/scripts/query-bugs.py \
  <WORKDIR>/analyze-ci-bug-candidates-<source1>.json \
  [<WORKDIR>/analyze-ci-bug-candidates-<source2>.json ...] \
  --workdir <WORKDIR>
```

Pass ALL per-source candidate files produced in Step 1. The script:

1. Checks for cached results from a prior run — if output files already exist and cover all candidates, skips JIRA queries and exits. To force fresh queries, delete the bug mapping files: `rm <WORKDIR>/analyze-ci-bugs-*.json`
2. Searches JIRA for each candidate using keyword queries, test case ID queries (bare + OCP-prefixed), and regression checks against closed/verified issues
3. Fetches all open bugs with the `microshift-ci-ai-generated` label
4. Writes one `<WORKDIR>/analyze-ci-bugs-<source>.json` per input file

**Error handling**: If the script exits non-zero, relay its error message to the user and stop.

The output files use this JSON format:

```json
{
  "source": "<source>",
  "date": "YYYY-MM-DD",
  "candidates": [
    {
      "error_signature": "<error_signature>",
      "severity": <N>,
      "failure_type": "<build|test|infrastructure>",
      "step_name": "<step_name>",
      "affected_jobs": <count for this source>,
      "duplicates": [
        {"key": "<JIRA-KEY>", "summary": "<summary>", "status": "<status>", "assignee": "<display_name>", "updated": "<YYYY-MM-DD>"}
      ],
      "regressions": [
        {"key": "<JIRA-KEY>", "summary": "<summary>", "status": "<status>", "assignee": "<display_name>", "updated": "<YYYY-MM-DD>"}
      ]
    }
  ],
  "open_bugs": [
    {
      "key": "USHIFT-1234",
      "summary": "...",
      "status": "In Progress",
      "priority": "Normal",
      "assignee": "jdoe",
      "created": "2026-05-01",
      "updated": "2026-05-09"
    }
  ]
}
```

The script writes these files in both dry-run and create modes. They enable `create-report.py` to show linked bugs in the HTML report, and are consumed by the merge step (Step 2a) for Jira-based deduplication.

### Step 2a: Merge Candidates

Run the merge script (even for a single source — it produces a unified output with Jira data injected from the bug mapping files written in Step 2).

Before invoking, also check for any `analyze-ci-bug-candidates-rebase-*.json` files in `<WORKDIR>`. If found, include them in the merge so rebase PR failures are deduplicated against release failures.

```text
python3 plugins/microshift-ci/scripts/search-bugs.py --merge <WORKDIR>/analyze-ci-bug-candidates-<source1>.json [<source2>.json ...] [<WORKDIR>/analyze-ci-bug-candidates-rebase-*.json] --output <WORKDIR>/analyze-ci-bug-candidates-merged-<SOURCE_TAG>.json --workdir <WORKDIR>
```

This writes `<WORKDIR>/analyze-ci-bug-candidates-merged-<SOURCE_TAG>.json`. Read and use this file for all subsequent steps.

### Step 3: Act on Auto-Decisions

The merged file from Step 2a contains a `results` array with pre-computed auto-decisions for each candidate. Each entry has `error_signature`, `action` (`create`/`update`/`skip`), `jira_key`, `skip_category`, and `reason`.

**Actions**:

1. **In dry-run mode** (`--create` NOT specified):
   - Do NOT display individual candidates to the user — the report in Step 5 handles that
   - Do NOT create any issues. Do NOT proceed to Steps 4/4b
   - Write the results file and continue to Step 5

2. **In create mode** (`--create` specified):
   - For candidates where action is `"create"`: proceed to Step 4
   - For candidates where action is `"update"`: proceed to Step 4b
   - For candidates where action is `"skip"`: move to next
   - Continue to Step 5

#### Results JSON

Copy the `results` array from the merged file into a new results file at `<WORKDIR>/analyze-ci-bug-results-<SOURCE_TAG>.json`:

```json
{
  "mode": "dry-run",
  "date": "YYYY-MM-DD",
  "results": [...]
}
```

Set `mode` to `"dry-run"` or `"create"` matching the current run mode. Set `date` to today's date (YYYY-MM-DD). In create mode, update each result entry's `jira_key` after creating/updating bugs (Steps 4/4b), and change `action` to `"failed"` if a MCP call fails. Step 4b may also demote `"update"` to `"skip"` with `skip_category="up_to_date"` during comment deduplication.

### Step 4: Create Bug via MCP (create mode only)

**Actions**:
For each candidate where the auto-decision is "create":

1. **Construct the bug summary**:
   - Format: `"MicroShift CI: <error_signature>"` (truncate to 100 chars if needed)

2. **Construct the bug description** using **Markdown** format (the MCP Jira tool accepts Markdown and automatically converts it to Jira wiki markup — do NOT write Jira wiki markup directly):

   `````text
   ## Description of problem

   CI job failures detected across MicroShift releases: <release1>, <release2>, ...

   <concise description derived from the error signature and analysis text>

   ## Version-Release number of selected component (if applicable)

   <release1>, <release2>, ...

   ## How reproducible

   Always (fails consistently in CI across multiple releases)

   ## Steps to Reproduce

   1. Run the CI job(s) listed below
   2. Observe failure in step: <step_name>

   ## Actual results

   ````

   <error details extracted from the analysis text — the specific error message and relevant log context>

   ````

   ## Expected results

   CI job should pass successfully.

   ## Additional info

   **Stack Layer:** <stack_layer>
   **CI Step:** <step_name>
   **Error Severity:** <severity>/5
   **Number of affected jobs:** <total count across all releases>
   **Last observed:** <latest finished date across all jobs, YYYY-MM-DD>
   **Affected Releases:** <release1> (<N> jobs), <release2> (<N> jobs)

   **Affected Jobs:**
   <for each release>
   *<release>:*
   <for each job in release>
   - [<job_name>](<job_url>)
   </for each>
   </for each>

   {{if the result's reason starts with "Potential regression of"}}
   **Regression Warning:** {{reason}} — this failure may be a recurrence of a previously fixed issue.
   {{end if}}

   **Source:** Auto-generated by /microshift-ci:create-bugs from CI analysis output.
   `````

3. **Create the issue**:

   ```python
   mcp__jira__jira_create_issue(
       project_key="USHIFT",
       summary="MicroShift CI: <error_signature>",
       issue_type="Bug",
       description="<constructed description>",
       components="MicroShift",
       additional_fields={
           "labels": ["microshift-ci-ai-generated"]
       }
   )
   ```

4. **Record the result**: Store the created issue key for the final report.

**Error Handling**:

- If MCP call fails, log the error, record the candidate as `"failed"` in the report, and continue to the next candidate. Do NOT prompt or retry.

### Step 4b: Update Existing Bug with Comment (create mode only)

**Precondition**: The candidate's action is `update` and `jira_key` is set (from the auto-decision in the merged file).

**Actions**:
For each candidate where action is "update":

1. **Comment deduplication** — check whether the bug already has up-to-date CI data:

   a. Fetch the target bug's comments:

      ```python
      mcp__jira__jira_get_issue(issue_key="<JIRA-KEY>", fields="comment", comment_limit=100)
      ```

   b. Find the most recent comment containing the marker string `"CI Doctor: New occurrences detected"`.

   c. Extract the `**Last observed:**` date (YYYY-MM-DD) from that comment.

   d. If no CI Doctor comment exists, check the bug description as a fallback: if it contains `"CI job failures detected across MicroShift releases"` (i.e., it was created by CI Doctor), extract the `**Last observed:**` date from the description instead.

   e. Compare against the candidate's most recent job `finished` date:
      - If **all** job `finished` dates are **on or before** the last-observed date → the bug is already up-to-date. Change the action to `"skip"` with `skip_category="up_to_date"` and reason `"Already up-to-date on <JIRA-KEY> (last observed <YYYY-MM-DD>)"`. Move to the next candidate.
      - If **any** job `finished` date is **after** the last-observed date, or no last-observed date was found → proceed to post the comment.

2. **Construct the update comment**:

   ```text
   ## CI Doctor: New occurrences detected

   This failure continues to be observed in CI.

   **Error Signature:** <error_signature>
   **Error Severity:** <severity>/5
   **Number of affected jobs:** <count>
   **Last observed:** <latest finished date>

   **Affected Releases:**
   - <release1> (<N> jobs)
   - <release2> (<N> jobs)

   **Affected Jobs:**
   - [<job_name>](<job_url>)
   ...

   Updated automatically by /microshift-ci:create-bugs.
   ```

3. **Post the comment**:

   ```python
   mcp__jira__jira_add_comment(
       issue_key="<JIRA-KEY>",
       body="<update comment>"
   )
   ```

4. **Record the result**: Store the updated issue key for the final report.

**Error Handling**:

- If MCP call fails, log the error, record the candidate as `"failed"` in the report, and continue to the next candidate. Do NOT prompt or retry.

### Step 4c: Update Bug Mapping Files (create mode only)

**Precondition**: At least one candidate had action `create` in Step 4. (`update` actions only add a comment and do not require mapping file updates.)

After all bugs are created, update the per-source bug mapping files (`<WORKDIR>/analyze-ci-bugs-<source>.json`) so that newly created bugs are reflected in the JIRA data consumed by the HTML report generator.

**Actions**:

1. **Collect new bugs**: Gather all candidates where action was `create`. For each, record the `jira_key`, `error_signature`, and the summary used in creation.

2. **Update each mapping file**: For every `<WORKDIR>/analyze-ci-bugs-<source>.json` file (all sources, not just the current one):

   a. **Add to `open_bugs`**: Append each new bug to the `open_bugs` array (skip if the key already exists):

      ```json
      {
        "key": "USHIFT-XXXX",
        "summary": "MicroShift CI: <error_signature>",
        "status": "To Do",
        "priority": "Undefined",
        "assignee": "Unassigned",
        "created": "<today YYYY-MM-DD>",
        "updated": "<today YYYY-MM-DD>"
      }
      ```

   b. **Add to `duplicates`**: Find the candidate entry in the file's `candidates` array whose `error_signature` matches. If found, append the new bug to its `duplicates` array (skip if the key already exists):

      ```json
      {"key": "USHIFT-XXXX", "summary": "MicroShift CI: <error_signature>", "status": "To Do", "assignee": "Unassigned", "updated": "<today YYYY-MM-DD>"}
      ```

   c. **Write the updated file** back to disk.

3. **Skip if no bugs were created**: If all candidates were skipped or failed, do not modify mapping files.

### Step 5: Generate Results Report (Deterministic Script)

**Actions**:

1. Ensure `<WORKDIR>/analyze-ci-bug-results-<SOURCE_TAG>.json` was written in Step 3
2. Generate the report:

   ```text
   python3 plugins/microshift-ci/scripts/search-bugs.py \
     --report <WORKDIR>/analyze-ci-bug-results-<SOURCE_TAG>.json \
     --candidates <WORKDIR>/analyze-ci-bug-candidates-merged-<SOURCE_TAG>.json \
     --workdir <WORKDIR>
   ```

3. Display the report output to the user

## Examples

### Example 1: Dry-Run for a Release (Default)

```bash
/microshift-ci:create-bugs 4.22
```

Shows what bugs would be created from release 4.22 analysis without creating anything.

### Example 2: Dry-Run for a PR

```bash
/microshift-ci:create-bugs pr-6396
```

Shows what bugs would be created from PR #6396 analysis.

### Example 3: Create Bugs for a Rebase PR

```bash
/microshift-ci:create-bugs rebase-release-4.22 --create
```

Resolves the rebase PR for release 4.22, then creates bugs.

### Example 4: Multi-Source Dry-Run

```bash
/microshift-ci:create-bugs main,4.22,4.21,4.20,5.0
```

Shows all failures across 5 releases with cross-release dedup applied. Failures appearing in multiple releases are merged into single candidates with `Releases:` lines.

### Example 5: Multi-Source Create

```bash
/microshift-ci:create-bugs main,4.22,4.21,4.20,5.0 --create
```

Creates bugs across all releases, updating existing Jira duplicates and skipping infrastructure failures. Cross-release duplicates are merged into single bugs referencing all affected releases.

### Example 6: No Job Files Found

```bash
/microshift-ci:create-bugs 4.19
```

```text
Error: No job analysis files found at <WORKDIR>/analyze-ci-release-4.19-job-*.txt

Run the analysis first:
  /microshift-ci:doctor 4.19
```

## Notes

- This command does NOT run CI analysis — it only consumes existing analysis files from `<WORKDIR>`
- Supports two file naming patterns:
  - Release jobs: `analyze-ci-release-<release>-job-*.txt` (from `/microshift-ci:doctor`)
  - PR jobs: `analyze-ci-prs-job-*-pr<number>-*.txt` (from `/microshift-ci:doctor`)
- Dry-run is the default to prevent accidental bug creation
- The `--create` flag enables actual bug creation and updating
- Candidates are always merged via `search-bugs.py --merge` (even for a single source) to produce a unified output with Jira data injected. Cross-release deduplication uses fuzzy signature matching (token-based Jaccard similarity, 50% threshold)
- Infrastructure failures (`failure_type: "infrastructure"`) are automatically skipped — these are transient CI/cloud issues, not product bugs. Classification uses the same step-name-based logic as the HTML report (`classify_breakdown` in `classify.py`)
- Bugs are created in USHIFT with component "MicroShift"; duplicate search covers both USHIFT and OCPBUGS
- All created bugs are labeled with `microshift-ci-ai-generated` for tracking
- The STRUCTURED SUMMARY block in job files is required — this is a contract with `/microshift-ci:prow-job`
- Machine-readable bug mapping files (`analyze-ci-bugs-<source>.json`) are written per source in Step 2 (both dry-run and create modes). They serve two purposes: (1) consumed by `create-report.py` to show JIRA bug links in the HTML report, and (2) consumed by `--merge` in Step 2a for Jira-based deduplication across releases

## Related Skills

- **microshift-ci:doctor**: Produces job analysis files consumed by this command
- **microshift-ci:prow-job**: Command that produces individual job reports with STRUCTURED SUMMARY
- **jira:create-bug**: Single bug creation skill (not used here — we call MCP directly)
- **microshift-ci:close-stale-bugs**: Closes stale unlinked bugs (should run after this skill)
