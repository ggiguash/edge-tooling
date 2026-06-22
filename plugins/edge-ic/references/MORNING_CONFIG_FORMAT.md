# Morning Config Format

Configuration for the `edge-ic:morning` skill, stored at `$HOME/.config/edge-ic/morning.yaml`.

## Structure

```yaml
title: "Morning Edge"  # text rendered as block pixel title banner

daily_notes:
  enabled: true
  path: "$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md"
  format: auto  # auto | todo | freeform

jira:
  username: "user@example.com"
  qa_statuses: ["ON_QA"]
  qa_components: []  # empty = all components; e.g. ["Two Node Fencing", "LVMS"]
  board_ids: ["11479"]

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
  review_queue: true
  rhel_queue: false
  quarterly_reminders: true
```

## Fields

| Field | Required | Default | Purpose |
|-------|----------|---------|---------|
| `title` | no | `Morning Edge` | Text rendered as block pixel title banner (▀▄█). Multi-word titles stack vertically. |
| `daily_notes.enabled` | yes | `true` | Whether to check daily notes for carry-over |
| `daily_notes.path` | if enabled | `$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md` | Path template with date placeholders |
| `daily_notes.format` | no | `auto` | `auto` detects format; `todo` for checkbox-based; `freeform` for keyword-based |
| `jira.username` | yes | inferred from MCP config | JIRA email for assignee queries |
| `jira.qa_statuses` | no | `["ON_QA"]` | Statuses that mean "ready for QA" in the QA Contact section |
| `jira.qa_components` | no | `[]` (all) | Filter QA tasks to specific components (e.g., `["Two Node Fencing", "LVMS"]`) |
| `jira.board_ids` | yes | auto-discovered | List of agile board IDs for sprint queries (e.g., `["11479", "12345"]`) |
| `github.username` | yes | inferred from git/gh | GitHub username for PR matching |
| `rhel_verification.enabled` | yes | `false` | Whether to check RHEL verification queue |
| `rhel_verification.project` | if enabled | `RHEL` | JIRA project key |
| `rhel_verification.summary_filter` | if enabled | `[TNF]` | Summary search string |
| `rhel_verification.component` | if enabled | `resource-agents` | Component filter |
| `sections.*` | no | `true` (except `rhel_queue`: `false` when RHEL verification is disabled) | Toggle individual sections on/off. Available: `qa_tasks`, `sprint_backlog`, `carry_over`, `open_prs`, `review_queue`, `rhel_queue`, `quarterly_reminders` |

## Date Placeholders

In `daily_notes.path`, these are replaced at runtime:
- `{YYYY}` — 4-digit year
- `{MM}` — 2-digit month (zero-padded)
- `{DD}` — 2-digit day (zero-padded)
- `{YYYY-MM-DD}` — full ISO date
