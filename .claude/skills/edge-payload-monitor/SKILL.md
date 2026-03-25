---
name: edge-payload-monitor
description: Monitor OpenShift nightly payloads for edge topology (SNO/TNA/TNF) failures with AI-enriched analysis
argument-hint: [--versions 4.18,4.19,4.20,4.21,4.22,4.23] [--skip-prow] [--skip-sippy]
user-invocable: true
---

# Edge Payload Monitor Skill

You are helping a developer monitor OpenShift nightly payload health for edge topologies (SNO, TNA, TNF). This skill orchestrates the `payload-monitor` Python tool and existing marketplace CI skills to generate an interactive HTML dashboard report with AI-powered root cause analysis for blocking job failures.

## Existing Skills Reference

This skill composes with the following installed marketplace CI skills from the [ai-helpers](https://github.com/openshift-eng/ai-helpers) repository. These are used automatically for blocking job analysis:

### Data Fetching Skills
| Skill | When to Use |
|-------|-------------|
| `ci:fetch-payloads` | Fetch recent release payloads from the release controller — use as a cross-check or when the Python tool's data needs supplementation |
| `ci:fetch-releases` | Fetch available OpenShift releases from Sippy — use to auto-discover active streams |
| `ci:fetch-test-report` | Fetch test report from Sippy with pass rates, test ID, and Jira component — use for per-test regression detail |
| `ci:fetch-job-run-summary` | Fetch a Prow job run summary with all failed tests grouped by SIG — use to understand failure scope |
| `ci:fetch-prowjob-json` | Fetch key data from a Prow job's prowjob.json artifact — use for job metadata |
| `ci:fetch-new-prs-in-payload` | Fetch PRs new in a payload compared to previous — use to identify suspect PRs causing regressions |
| `ci:fetch-regression-details` | Fetch detailed Component Readiness regression info from Sippy — use for Sippy regressions |
| `ci:fetch-related-triages` | Fetch existing triages and untriaged regressions related to a given regression — use to avoid duplicate work |
| `ci:fetch-jira-issue` | Fetch JIRA issue details including status, assignee, comments, and progress classification — use for enriched bug context |
| `ci:fetch-test-runs` | Fetch test runs from Sippy including outputs for AI similarity analysis — use to compare failure patterns |

### Deep Analysis Skills
| Skill | When to Use |
|-------|-------------|
| `ci:analyze-payload` | Full payload analysis with historical lookback and HTML report — use for rejected/failing payloads with edge blockers |
| `ci:prow-job-analyze-test-failure` | Analyze failed tests by inspecting test code, downloading artifacts, and optionally integrating must-gather — use for any failing edge test |
| `ci:prow-job-analyze-install-failure` | Analyze OpenShift install failures from installer logs, log bundles, and sosreports — use when edge jobs fail at install stage |
| `ci:prow-job-analyze-metal-install-failure` | Analyze bare metal install failures using dev-scripts artifacts — use for metal/baremetal SNO or TNF jobs with "metal" in name |
| `ci:prow-job-analyze-resource` | Analyze K8s resource lifecycle in Prow job artifacts (audit logs, pod logs) — use when failure involves resource state issues |
| `ci:prow-job-artifact-search` | Search, list, and fetch artifacts from Prow job runs in GCS — use when you need to find specific artifacts |
| `ci:prow-job-extract-must-gather` | Extract and decompress must-gather archives — use when cluster diagnostics are needed |
| `ci:analyze-regression` | Analyze Component Readiness regression details and suggest next steps — use for Sippy-detected regressions |
| `ci:check-if-jira-regression-is-ongoing` | Check if a JIRA regression bug is still ongoing or resolved — use to validate whether known bugs still apply |

### Action Skills
| Skill | When to Use |
|-------|-------------|
| `ci:set-release-blocker` | Set Release Blocker field on a JIRA issue — use when an edge failure is blocking payload acceptance |
| `ci:triage-regression` | Create or update a Component Readiness triage record — use when a Sippy regression needs to be triaged |
| `ci:revert-pr` | Revert a merged PR breaking CI/payloads — use when a specific PR is identified as the root cause |
| `ci:trigger-payload-job` | Trigger payload testing on a PR — use to verify a fix resolves the payload failure |

---

## Workflow

### Step 1: Parse Arguments

Parse `$ARGUMENTS` to determine options:

- **`--versions X,Y,Z`**: Override which OCP versions to monitor (e.g., `--versions 4.18,4.19`)
- **`--skip-prow`**: Skip Prow artifact fetching (faster, less detail)
- **`--skip-sippy`**: Skip Sippy regression check
- If `$ARGUMENTS` is empty: use defaults (all configured versions)

### Step 2: Run the Python Tool

Run the payload monitor Python tool to collect data and generate the base report:

```bash
cd payload-monitor && python -m payload_monitor --output reports/report-$(date +%Y-%m-%d).html [OPTIONS]
```

Pass through any relevant flags (`--versions`, `--skip-prow`, `--skip-sippy`).

The tool always outputs:
- An HTML report (self-contained interactive dashboard)
- A JSON data file (same path with `.json` extension)
- A blocking summary file (`.blocking.json`) — a small file listing only failing blocking jobs with their prow URLs, topology, version, and payload tag

### Step 3: Read Blocking Summary and Analyze Failures

Read the small `reports/report-{date}.blocking.json` file (**not** the full JSON — this saves tokens). It contains only the failing blocking edge jobs:

```json
[
  {
    "job_name": "periodic-ci-...-sno-...",
    "prow_url": "https://prow.ci.openshift.org/view/gs/.../123",
    "topology": "SNO",
    "version": "4.19",
    "payload_tag": "4.19.0-0.nightly-2026-03-25-085944"
  }
]
```

If the file does not exist or is empty, skip to Step 5 (no blocking failures to analyze).

**For informing job failures:** Do NOT run deep analysis. The HTML report already includes a suggestion to use Claude directly with `/ci:prow-job-analyze-test-failure <prow-url>`.

#### Multi-Agent Orchestration (2+ blocking failures)

When there are **2 or more** blocking failures, use the Agent tool to analyze them **in parallel** — one subagent per blocking job. This significantly reduces wall-clock time.

For each blocking job, spawn a subagent with this prompt:

```
Analyze this failing blocking edge job and return a JSON deep_analysis object.

Job: {job_name}
Prow URL: {prow_url}
Topology: {topology}
Version: {version}
Payload: {payload_tag}

Steps:
1. Use `ci:fetch-job-run-summary` with the Prow URL to get all failed tests grouped by SIG
2. Use `ci:fetch-prowjob-json` with the Prow URL to get job metadata

Then based on failure type:
- If install failure (error contains "install should succeed", "bootstrap", or failed in pre/setup phase):
  Use `ci:prow-job-analyze-install-failure` (or `ci:prow-job-analyze-metal-install-failure` if job name contains "metal")
- If test failure (job passed install but failed during test phase):
  Use `ci:prow-job-analyze-test-failure`
- If resource/state failure (etcd issues, operator degraded, node not ready):
  Use `ci:prow-job-analyze-resource`

For payload context: use `ci:fetch-new-prs-in-payload` to identify suspect PRs.
For JIRA context: use `ci:fetch-jira-issue` for any linked bugs.

Return ONLY a JSON object with these fields:
{
  "prow_url": "{prow_url}",
  "root_cause": "One-sentence explanation",
  "failure_type": "Infrastructure flake | Test regression | Install failure | Platform issue",
  "impact": "How this affects payload acceptance and which topologies",
  "suspect_prs": ["https://github.com/org/repo/pull/123"],
  "recommendation": "Specific next action"
}
```

Launch all subagents in parallel using multiple Agent tool calls in the same response. Collect their results and proceed to Step 4.

#### Single-Agent Analysis (1 blocking failure)

When there is exactly **1 blocking failure**, analyze it directly in the main agent (no subagent). The overhead of spawning a subagent provides no benefit for a single job — it adds latency from context setup without any parallelism gain.

Run the same analysis steps inline:

1. Use `ci:fetch-job-run-summary` to get all failed tests grouped by SIG
2. Use `ci:fetch-prowjob-json` to get job metadata

Then branch based on failure type:

- **Install failure** (error contains "install should succeed", "bootstrap", or job failed in pre/setup phase):
  Use `ci:prow-job-analyze-install-failure` for standard install failures.
  Use `ci:prow-job-analyze-metal-install-failure` if the job name contains "metal" (common for SNO/TNF baremetal jobs).
- **Test failure** (job passed install but failed during test phase):
  Use `ci:prow-job-analyze-test-failure` to inspect test code, download artifacts, and identify root cause.
- **Resource/state failure** (etcd issues, operator degraded, node not ready — common in two-node topologies):
  Use `ci:prow-job-analyze-resource` to trace K8s resource lifecycle via audit logs.
  Use `ci:prow-job-extract-must-gather` if must-gather archives are available.

For payload-level context: use `ci:fetch-new-prs-in-payload` to identify suspect PRs.
For JIRA context: use `ci:fetch-jira-issue` for any linked bugs, `ci:check-if-jira-regression-is-ongoing` for known regressions.

### Step 4: Write Analysis File

Collect the deep analysis results (from subagents or inline analysis) and write a small analysis-only JSON file keyed by `prow_url` to `reports/analysis-{date}.json`:

```json
{
  "ai_cost": "$X.XX (N input + M output tokens)",
  "by_prow_url": {
    "https://prow.ci.openshift.org/view/gs/.../123": {
      "root_cause": "One-sentence explanation of the root cause",
      "failure_type": "Infrastructure flake | Test regression | Install failure | Platform issue",
      "impact": "How this affects payload acceptance and which topologies",
      "suspect_prs": ["https://github.com/org/repo/pull/123"],
      "recommendation": "Specific next action (file bug, wait for fix, investigate PR, etc.)"
    }
  }
}
```

This file is intentionally small — it contains only the AI analysis results, not the full report data. This minimizes token usage.

### Step 5: Regenerate HTML with Deep Analysis

Re-run the Python tool to merge the analysis and regenerate the HTML report:

```bash
cd payload-monitor && python -m payload_monitor \
  --from-json reports/report-$(date +%Y-%m-%d).json \
  --merge-analysis reports/analysis-$(date +%Y-%m-%d).json \
  --output reports/report-$(date +%Y-%m-%d).html
```

The `--merge-analysis` flag merges the small analysis file into the report by matching prow URLs, then regenerates the HTML with "AI Root Cause Analysis" cards for each analyzed job.

If there were no blocking failures (no analysis file), skip `--merge-analysis`:

```bash
cd payload-monitor && python -m payload_monitor \
  --from-json reports/report-$(date +%Y-%m-%d).json \
  --output reports/report-$(date +%Y-%m-%d).html
```

### Step 6: Present Output

Do NOT duplicate the report data or findings summary — the HTML dashboard already contains all of that. Present only a brief confirmation:

```
## Edge Payload Monitor Report Generated

Report: `payload-monitor/reports/report-{date}.html`
JSON:   `payload-monitor/reports/report-{date}.json`

Analyzed {N} blocking job failure(s) with AI root cause analysis.
Open the HTML report for the full interactive dashboard with findings summary, suggested actions, and detailed analysis.
```

Offer follow-up actions the user can take from this session:
- **Create JIRA bugs** for untracked failures
- **Set release blocker** on a JIRA issue (`ci:set-release-blocker`)
- **Triage a regression** in Component Readiness (`ci:triage-regression`)
- **Trigger payload job** to test a fix (`ci:trigger-payload-job`)
- **Investigate an informing job** further (`ci:prow-job-analyze-test-failure`)

---

## Important Notes

- The Python tool must be run from the `payload-monitor/` directory
- Dependencies: `pip install -r requirements.txt` (requests, jinja2, pyyaml, click)
- JIRA features require `JIRA_TOKEN` and `JIRA_USER` environment variables (get a token from [JIRA API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens))
- Prow artifact fetching requires `gsutil` (Google Cloud SDK)
- Do NOT modify the Python source code — this skill is an orchestration layer on top
- Do NOT duplicate report data in your output — the HTML dashboard is the primary output, keep your response brief
- Deep analysis runs automatically for **blocking jobs only** — informing jobs get a Claude suggestion instead
- Prioritize blocking failures over informing failures in all analysis
- Flag recurring failures prominently — 2+ payload recurrence strongly suggests a real regression, not a flake
- For TNF/TNA failures, pay special attention to etcd, Pacemaker, and fencing-related errors
- For SNO failures, check for single-node-specific issues like workload partitioning, resource constraints
- When multiple edge topologies fail in the same payload, investigate whether it's a shared platform issue vs topology-specific
