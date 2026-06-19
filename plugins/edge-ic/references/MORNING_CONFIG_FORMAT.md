# Morning Config Format

Configuration for the `edge-ic:morning` skill, stored at `$HOME/.config/edge-ic/morning.yaml`.

## Structure

```yaml
daily_notes:
  enabled: true
  path: "$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md"
  format: auto  # auto | todo | freeform

jira:
  username: "user@example.com"
  watch_statuses: ["ON_QE"]
  board_id: "11479"

github:
  username: "ghuser"

rhel_verification:
  enabled: false
  project: "RHEL"
  summary_filter: "[TNF]"
  component: "resource-agents"

sections:
  qa_tasks: true
  sprint_backlog: true
  carry_over: true
  open_prs: true
  rhel_queue: false
  quarterly_reminders: true
```

## Fields

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `daily_notes.enabled` | yes | `true` | Whether to check daily notes for carry-over |
| `daily_notes.path` | if enabled | `$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md` | Path template with date placeholders |
| `daily_notes.format` | no | `auto` | `auto` detects format; `todo` for checkbox-based; `freeform` for keyword-based |
| `jira.username` | yes | inferred from MCP config | JIRA email for assignee queries |
| `jira.watch_statuses` | no | `["ON_QE"]` | Statuses for QA Contact section (advanced — most users keep default) |
| `jira.board_id` | yes | auto-discovered | Agile board ID for sprint queries |
| `github.username` | yes | inferred from git/gh | GitHub username for PR matching |
| `rhel_verification.enabled` | yes | `false` | Whether to check RHEL verification queue |
| `rhel_verification.project` | if enabled | `RHEL` | JIRA project key |
| `rhel_verification.summary_filter` | if enabled | `[TNF]` | Summary search string |
| `rhel_verification.component` | if enabled | `resource-agents` | Component filter |
| `sections.*` | no | `true` (except `rhel_queue`: `false` when RHEL verification is disabled) | Toggle individual sections on/off |

## Date Placeholders

In `daily_notes.path`, these are replaced at runtime:
- `{YYYY}` — 4-digit year
- `{MM}` — 2-digit month (zero-padded)
- `{DD}` — 2-digit day (zero-padded)
- `{YYYY-MM-DD}` — full ISO date
