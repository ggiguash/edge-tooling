# Edge Payload Monitor

Automated monitoring tool for OpenShift nightly payload health across edge topologies (SNO, TNA, TNF). Fetches data from the amd64 release controller, Sippy Component Readiness, Prow CI, and JIRA to produce an interactive HTML dashboard.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with defaults (auto-discovers active OCP streams)
python -m payload_monitor

# Run and open report in browser
python -m payload_monitor --open

# Override versions
python -m payload_monitor --versions 4.18,4.19,4.20,4.21,4.22,4.23

# Regenerate HTML from JSON with AI analysis merged in
python -m payload_monitor --from-json reports/report-2026-03-25.json --merge-analysis reports/analysis-2026-03-25.json --output my-report.html
```

Or use the convenience wrapper:

```bash
./payload-monitor.sh
```

## What It Does

1. **Fetches nightly payloads** from the [amd64 release controller](https://amd64.ocp.releases.ci.openshift.org) for active OCP nightly streams (auto-discovered from both Sippy and the release controller, currently 4.18 through 5.0)
2. **Filters for edge topology jobs** (SNO, TNA, TNF) in blocking and informing job results
3. **Analyzes failures** by fetching Prow job logs and extracting failing test names and error signatures
4. **Queries Sippy** Component Readiness for regressions between HA and edge variants
5. **Searches JIRA** for existing bugs matching failure signatures
6. **Generates an HTML dashboard** with:
   - Overall health summary per OCP version
   - Payload timeline with color-coded status
   - Failing job details with log excerpts
   - Linked JIRA bugs with status badges
   - Suggested new bugs with pre-filled "Create in JIRA" links

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
          +------------------+------------------+
          |                  |                  |
+---------v------+  +--------v-------+  +------v--------+
| Release Ctrl   |  |    Sippy       |  |     JIRA      |
| Collector      |  |   Collector    |  |   Collector   |
+--------+-------+  +----------------+  +---------------+
         |
+--------v-------+
|  Prow Collector |
+----------------+
         |
+--------v-------+
| HTML Dashboard  |
+----------------+
```

### Two-Layer Design

**Layer 1 (this tool)**: Python CLI that collects data, analyzes failures, and generates HTML reports.

**Layer 2 (Claude Code skill)**: `/edge-payload-monitor` skill that orchestrates this tool plus existing marketplace CI skills (from the [ai-helpers](https://github.com/openshift-eng/ai-helpers) Red Hat repository) for AI-powered root cause summarization.

## Configuration

Edit `config.yaml` to customize behavior:

```yaml
versions:
  auto_discover: true       # auto-discover active nightly streams
  override: []              # or specify: ["4.18", "4.19", "4.20", "4.21", "4.22", "4.23", "5.0"]

topologies:
  - name: SNO
    job_patterns: ["sno", "single-node", "metal-single-node"]
    exclude_patterns: ["telco"]
  - name: TNA
    job_patterns: ["two-node", "tna"]
    exclude_patterns: ["telco"]
  - name: TNF
    job_patterns: ["tnf", "two-node-fencing"]
    exclude_patterns: ["telco"]

payloads_per_stream: 5      # recent payloads to analyze per stream

jira:
  project: "OCPBUGS"
  component: "Edge Enablement"

output:
  report_dir: "./reports"

slack:                       # future feature
  webhook_url: ""
  channel: "#edge-enablement-payload-manager"
  enabled: false
```

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `JIRA_TOKEN` | For JIRA features | Personal access token for issues.redhat.com |
| `JIRA_USER` | For JIRA features | JIRA username (email) |

To obtain a JIRA token, go to your [JIRA Personal Access Tokens](https://id.atlassian.com/manage-profile/security/api-tokens) page and create a new token.

Set them in your shell before running:

```bash
export JIRA_TOKEN="your-token-here"
export JIRA_USER="your-email@redhat.com"
```

Or add them to `~/.bashrc` / `~/.zshrc` for persistence.

## CLI Reference

```
Usage: python -m payload_monitor [OPTIONS]

Options:
  --config PATH        Config file path (default: config.yaml)
  --versions TEXT      Override versions, comma-separated (e.g., "4.18,4.19")
  --output PATH        Output HTML file path (default: reports/report-YYYY-MM-DD.html)
  --from-json PATH     Regenerate HTML from a JSON file (skips data collection)
  --merge-analysis PATH  Merge a small analysis JSON into the report (use with --from-json)
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
| [Sippy](https://sippy.dptools.openshift.org) | `/api/releases`, `/api/jobs` | None | Version auto-discovery, job pass rates, regressions |
| [Prow](https://prow.ci.openshift.org) | Job API + GCS artifacts | None | Job logs, junit XMLs, failing test details |
| [JIRA](https://issues.redhat.com) | REST API v2 | Token | Existing bug search, bug creation links |

## Topology Job Patterns

Jobs are classified by topology based on name patterns:

- **SNO** (Single Node OpenShift): `sno`, `single-node`, `metal-single-node`
- **TNA** (Two Node Active): `two-node`, `tna`
- **TNF** (Two Nodes with Fencing): `tnf`, `two-node-fencing`

These patterns are configurable in `config.yaml`.

## Dashboard Features

The generated HTML report is a single self-contained file (no external dependencies) with:

- **Summary cards**: Pass/fail counts per OCP version, overall health indicator
- **Payload timeline**: Visual timeline of recent payloads, color-coded by status
- **Failing jobs table**: Sortable/filterable by version, topology, severity
- **Failure details**: Expandable cards with error messages and log excerpts
- **JIRA integration**: Linked existing bugs with status/assignee, suggested new bugs with create links
- **Filters**: Interactive filtering by OCP version, topology (SNO/TNA/TNF), and job type (blocking/informing)

## Scheduling

### Cron (daily at 6:00 AM UTC)

```bash
0 6 * * * cd /path/to/payload-monitor && python -m payload_monitor --output reports/daily-$(date +\%Y-\%m-\%d).html
```

### Claude Code (manual)

```
/edge-payload-monitor
```

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Run with verbose output
python -m payload_monitor --verbose
```

## Future Roadmap

- Slack notifications to `@edge-enablement-payload-manager` with daily report summary
- Web portal integration (serve reports via simple HTTP server)
- Historical trend database (SQLite) for cross-day analysis
- Claude skill for AI-powered root cause summarization
