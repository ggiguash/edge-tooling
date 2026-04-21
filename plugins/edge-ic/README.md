# Edge IC Plugin

Individual contributor workflow automation for TODO management, status reporting, and Jira updates.

## Commands

### `/edge-ic:daily-report`

Generate a daily standup report from today's TODO file in Slack-ready format.

**Usage:**

```text
/edge-ic:daily-report
```

**Output:**

- Plain text report with completed and in-progress items
- Slack emoji format (`:done-circle-check:`, `:in-progress:`, `:jira-blocker:`)
- Jira ticket links
- Ready for direct copying into Slack

---

### `/edge-ic:weekly-wrapup`

Generate a weekly summary from the past week's TODO files.

**Usage:**

```text
/edge-ic:weekly-wrapup
```

**Output:**

- Aggregated accomplishments from Monday-Friday
- Grouped by theme (bugs, features, process improvements, etc.)
- Jira ticket links
- Markdown format

---

### `/edge-ic:sprint-status`

Query all tickets in a sprint and display them grouped by status.

**Usage:**

```text
/edge-ic:sprint-status [sprint-number] [--assignee=<user>] [--format=<type>]
```

**Arguments:**

- `sprint-number`: Sprint number (e.g., `287`)
- `--assignee=<user>`: Filter by assignee (email, `currentUser()`, or `Unassigned`)
- `--format=<type>`: Output format (`table`, `simple`, `keys-only`)

**Examples:**

```text
/edge-ic:sprint-status 287
/edge-ic:sprint-status 287 --assignee=currentUser()
/edge-ic:sprint-status 287 --format=simple
```

---

### `/edge-ic:update-jira`

Read today's TODO file and update related Jira issues with accomplishments.

**Usage:**

```text
/edge-ic:update-jira
```

**Features:**

- Parses completed items from today's TODO
- Prompts for which issues to update
- Adds comments with accomplishment details
- Updates issue status if appropriate

## Installation

Add the edge-tooling marketplace to Claude Code:

```text
/plugin marketplace add openshift-eng/edge-tooling
```

Then install the edge-ic plugin:

```text
/plugin install edge-ic
```

## Requirements

- Jira MCP server configured for Jira commands
- TODO files in `.daily/YYYY/MM/YYYY-MM-DD.md` format (relative to repository root)

## Use Cases

- Daily standup reporting to Slack
- Weekly accomplishment summaries
- Sprint progress tracking
- Jira issue updates from TODO items
