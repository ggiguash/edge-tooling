# MicroShift CI Plugin

## Installation

```text
/plugin marketplace add openshift-eng/edge-tooling
/plugin install microshift-ci
```

## What Runs in CI

A periodic Prow job (`periodic-ci-openshift-eng-edge-tooling-main-microshift-ci-doctor`)
runs daily and performs these phases automatically:

1. **Analysis** — `/microshift-ci:doctor <releases>` (45 min, 100 turns)
2. **Bug creation** — `/microshift-ci:create-bugs <releases> --create --auto`
   (10 min, 50 turns)
3. **Fix test bugs dry-run** — `/microshift-ci:fix-test-bugs --open`
   (5 min, 20 turns) — reports which bugs are eligible for auto-fix
4. **Report refresh** — `/microshift-ci:doctor-refresh <releases>`
   (5 min, 30 turns) — re-generates the HTML report with new bug links
5. **Close duplicate rebase PRs** — closes older rebase PRs superseded by newer ones
6. **Rebase PR restart** — restarts failed rebase bot PR tests

The job produces an HTML report, per-job analysis files, bug mapping JSON,
and a session archive for local continuation. All artifacts are available
in the Prow job's artifact directory.

## Daily Workflow

The commands below use `<releases>` as a placeholder for the comma-separated
release list. The current CI default is `4.18,4.19,4.20,4.21,4.22,5.0,main`.

Start from the CI job results - don't re-run doctor locally.

### 1. Open the CI job

Find the latest run at
[MicroShift CI Doctor](https://prow.ci.openshift.org/?job=periodic-ci-openshift-eng-edge-tooling-main-microshift-ci-doctor).

The Prow Spyglass of a job page contains the `MicroShift CI Doctor Report`
section, which is the main entry point. The report shows all failures grouped
by release with JIRA correlation.

### 2. Continue locally

The Prow Spyglass of a job page contains the `Continue This MicroShift CI Session Locally`
section, containing the command for downloading the CI session artifacts into
a local working directory:

```text
/microshift-ci:continue-session <prow-job-url>
```

This sets up the same working directory layout the CI job used, so all subsequent
commands work on the downloaded data.

> Note: Only analysis files are downloaded - raw prow job artifacts
> (build logs, SOS reports) are not included. Use `/microshift-ci:prow-job`
> to fetch those for specific jobs.

### 3. Review bug candidates

```text
/microshift-ci:create-bugs <releases> --auto
```

Dry-run: shows what bugs would be created or skipped, with decisions
(duplicate, stale regression, infrastructure, or new).

### 4. Create bugs

```text
/microshift-ci:create-bugs <releases> --auto --create
```

Executes: creates JIRA bugs in USHIFT, skips duplicates and infrastructure failures.
Drop `--auto` for interactive per-candidate prompts.

### 5. Fix eligible bugs

```text
/microshift-ci:fix-test-bugs --open
```

Queries JIRA for all unresolved AI-generated bugs (`labels = microshift-ci-ai-generated`),
evaluates each against eligibility check gates, and reports which bugs can be
auto-fixed in `test/`, `scripts/`, or `docs/`.

Gates:

1. **No existing PR** — checks JIRA links and GitHub for OPEN/MERGED PRs
2. **In-scope files** — fix target must be in `test/`, `scripts/`, or `docs/`
3. **Code-fixable** — root cause is a test/script issue, not a product bug

To attempt fixes (opens draft PRs in openshift/microshift):

```text
/microshift-ci:fix-test-bugs --open --fix --auto
```

`--auto` auto-fixes HIGH confidence bugs; MEDIUM confidence bugs prompt for
confirmation. Each fix gets its own branch and draft PR for independent review.

Can also target specific bugs:

```text
/microshift-ci:fix-test-bugs USHIFT-1234,USHIFT-5678 --fix
```

### 6. Investigate specific failures

```text
/microshift-ci:prow-job <prow-url>
/microshift-ci:test-job <prow-url>
/microshift-ci:test-scenario <prow-url> <scenario-name>
```

- `prow-job` - root cause analysis of a single failed job
- `test-job` - comprehensive job metadata and all scenario results
- `test-scenario` - deep dive into one scenario's test results

### 7. Refresh report after changes

```text
/microshift-ci:doctor-refresh <releases>
```

Re-runs JIRA correlation and regenerates the HTML report from existing
job analysis files (does not re-analyze jobs).

## PR Job Management

The CI job automatically closes duplicate rebase PRs and restarts failed
rebase bot PR tests. To run manually:

```bash
# Close duplicate rebase PRs (dry-run)
bash plugins/microshift-ci/scripts/prow-jobs-for-pull-requests.sh \
  --mode close-duplicates --author 'microshift-rebase-script[bot]' \
  --filter 'NO-ISSUE: rebase-release'

# Close duplicate rebase PRs (execute)
bash plugins/microshift-ci/scripts/prow-jobs-for-pull-requests.sh \
  --mode close-duplicates --author 'microshift-rebase-script[bot]' \
  --filter 'NO-ISSUE: rebase-release' --execute

# Restart failed rebase PR jobs (dry-run)
bash plugins/microshift-ci/scripts/prow-jobs-for-pull-requests.sh \
  --mode restart --author 'microshift-rebase-script[bot]'

# Restart failed rebase PR jobs (execute)
bash plugins/microshift-ci/scripts/prow-jobs-for-pull-requests.sh \
  --mode restart --author 'microshift-rebase-script[bot]' --execute
```

## More Info

See the [plugin README](../../plugins/microshift-ci/README.md) for prerequisites,
full skill list, and usage examples.
