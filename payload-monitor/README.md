# Edge Enablement Payload Monitor

Automated monitoring tool for OpenShift nightly payload health across edge topologies (SNO, TNA, TNF). Fetches data from the amd64 release controller, Sippy Component Readiness, Prow CI, and JIRA to produce an interactive HTML dashboard.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with defaults (monitors versions 4.18 through 5.0)
python -m payload_monitor

# Run and open report in browser
python -m payload_monitor --open

# Override versions
python -m payload_monitor --versions 4.18,4.19,4.20,4.21,4.22,4.23

# Patch AI analysis into an existing HTML report
python -m payload_monitor --merge-analysis reports/analysis-2026-03-25.json --output reports/report-2026-03-25.html
```

## What It Does

1. **Fetches nightly payloads** from the [amd64 release controller](https://amd64.ocp.releases.ci.openshift.org) for OCP nightly streams (4.18 through 5.0 by default, overridable with `--versions`)
2. **Filters for edge topology jobs** (SNO, TNA, TNF) in blocking and informing job results
3. **Analyzes failures** by fetching Prow job logs and extracting failing test names and error signatures
4. **Queries Sippy** for job-level regressions (pass rate drops) across edge topologies
5. **Queries Component Readiness** for statistically significant regressions on Single Node vs HA topology
6. **Searches JIRA** for existing bugs matching failure signatures
7. **Generates an HTML dashboard** with health summaries, failure details, regressions, and JIRA integration

## Architecture

```
                    +-------------------+
                    |   CLI / Skill     |
                    +--------+----------+
                             |
                    +--------v----------+
                    |   Analyzer        |
                    +--------+----------+
                             |
     +------------+----------+----------+------------+
     |            |          |          |             |
+----v-------+ +--v------+ +v--------+ +v----------+ +v-----------+
| Release    | | Sippy   | | Comp.   | | JIRA      | | Prow       |
| Controller | | Jobs    | | Ready.  | | Collector | | Collector  |
+----+-------+ +---------+ +---------+ +-----------+ +-----+------+
     |                                                      |
     +------------------------------------------------------+
                             |
                    +--------v----------+
                    |  HTML Dashboard   |
                    +-------------------+
```

### Usage

**Standalone CLI**: Run `python -m payload_monitor` to collect data and generate an HTML dashboard.

**Claude Code skill**: Run `/ee-payload-monitor` to also get AI-powered root cause analysis for blocking job failures, using marketplace CI skills from [ai-helpers](https://github.com/openshift-eng/ai-helpers).

### Performance and Token Efficiency

- **Parallel data collection**: All data sources are queried concurrently using `ThreadPoolExecutor`:
  - Release Controller, Sippy, and Component Readiness APIs run in parallel (`__main__.py`)
  - Per-stream payload tag detail fetches run concurrently within each stream (`collectors/release_controller.py`)
  - Prow artifact enrichment (junit XML downloads) runs across failing jobs in parallel (`collectors/prow.py`)
  - JIRA bug searches run concurrently across all unique failing jobs (`collectors/jira.py`)
- **Shared HTTP sessions**: All collectors reuse persistent `requests.Session` instances with automatic retry (3 attempts) and exponential backoff for transient failures (429, 5xx).
- **No JSON round-trip**: AI analysis is patched directly into the existing HTML report instead of serializing/deserializing the full report data through JSON.
- **Minimal AI input**: Blocking job data is emitted to stdout via structured markers (`BLOCKING_JOBS_START`/`BLOCKING_JOBS_END`) — Claude reads only job names and Prow URLs, never the full report data. Deep analysis runs only on blocking job failures; informing jobs get a lightweight Claude suggestion instead.
- **Multi-agent parallelism**: When multiple blocking jobs need analysis, each is analyzed by a separate subagent in parallel.

## Configuration

Configuration is hardcoded in `payload_monitor/config.py`. The defaults are:

| Setting | Default | Override |
|---------|---------|----------|
| Versions | 4.18, 4.19, 4.20, 4.21, 4.22, 4.23, 5.0 | `--versions` CLI flag |
| Payloads per stream | 5 | — |
| JIRA project | OCPBUGS | — |
| Report directory | `./reports` | `--output` CLI flag |

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_TOKEN` | For JIRA features | Atlassian Cloud Personal Access Token (read-only) |

To obtain a token, go to [Atlassian API Tokens](https://id.atlassian.com/manage-profile/security/api-tokens) and create a new token. **Use read-only permissions** — this tool only searches for existing bugs and never creates or modifies JIRA issues. The "Create in JIRA" links open the browser for manual review before submission.

Set it in your shell before running:

```bash
export JIRA_TOKEN="your-pat-here"
```

Or add it to `~/.bashrc` / `~/.zshrc` for persistence.

## CLI Reference

```
Usage: python -m payload_monitor [OPTIONS]

Options:
  --versions TEXT      Override versions, comma-separated (e.g., "4.18,4.19")
  --output PATH        Output HTML file path (default: reports/report-YYYY-MM-DD.html)
  --from-json PATH     Regenerate HTML from a JSON file (skips data collection)
  --json               Also export full report data as JSON
  --merge-analysis PATH  Patch analysis JSON into an existing HTML report (or into --from-json data)
  --open               Open report in browser after generation
  --skip-prow          Skip Prow artifact fetching (faster, less detail)
  --skip-sippy         Skip Sippy regression check
  --verbose            Enable verbose logging
  --help               Show this message and exit
```

## Data Sources

| Source | API | Auth | Purpose |
|--------|-----|------|---------|
| [Release Controller](https://amd64.ocp.releases.ci.openshift.org) | `/api/v1/releasestream/*/tags` | None | Payload status, blocking/informing job results |
| [Sippy](https://sippy.dptools.openshift.org) | `/api/jobs` | None | Job pass rates, regressions |
| [Sippy Component Readiness](https://sippy.dptools.openshift.org/sippy-ng/component_readiness/main) | `/api/component_readiness` | None | HA vs Single Node topology regression detection |
| [Prow](https://prow.ci.openshift.org) | Job API + GCS artifacts | None | Job logs, junit XMLs, failing test details |
| [JIRA](https://redhat.atlassian.net) | REST API v3 | Token (read-only) | Existing bug search, bug creation links |

## Topology Job Patterns

Jobs are classified by topology based on name patterns:

- **SNO** (Single Node OpenShift): `sno`, `single-node`, `metal-single-node`
- **TNA** (Two Node Active): `two-node`, `tna`
- **TNF** (Two Nodes with Fencing): `tnf`, `two-node-fencing`

These patterns are defined in `payload_monitor/config.py`.

## Dashboard Features

The generated HTML report is a single self-contained file (no external dependencies) with:

- **Version health status**: Per-version health indicator with payload acceptance timeline
- **Findings summary**: Actionable summary with suggested next steps
- **Failing edge jobs**: Blocking and informing job failures across SNO/TNA/TNF topologies
- **Failure analysis**: Error messages, failing tests, and AI root cause analysis (when enriched via Claude skill)
- **Sippy job regressions**: Edge jobs with significant pass rate drops compared to previous periods
- **Component Readiness**: HA vs Single Node topology regressions detected by Fisher's exact test
- **JIRA integration**: Matching existing bugs and suggested new bugs with pre-filled create links

## How to run the tooling

### Terminal

```bash
python -m payload_monitor --output reports/daily-$(date +\%Y-\%m-\%d).html
```

### Claude Code skill

```
/ee-payload-monitor
```

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run with verbose output
python -m payload_monitor --verbose
```

## Future Roadmap

- Slack notifications to `@edge-enablement-payload-manager` with daily report summary
