---
name: edge-ic:morning
description: Surface your daily task list — QA-ready tickets, sprint backlog, carry-over items, open PRs, RHEL verification queue, and quarterly reminders. Use at the start of your day to see what needs attention.
allowed-tools:
  - Read
  - Bash
  - WebFetch
  - AskUserQuestion
  - mcp__mcp-atlassian__jira_search
  - mcp__mcp-atlassian__jira_get_agile_boards
  - mcp__mcp-atlassian__jira_get_sprints_from_board
  - mcp__mcp-atlassian__jira_get_sprint_issues
  - mcp__mcp-atlassian__jira_get_issue
user-invocable: true
argument-hint: "[--setup]"
---

# IC: Morning Briefing

Aggregate your daily task surface from JIRA, daily notes, PR dashboards, and calendar into a single prioritized morning briefing.

## Step 0: Parse Arguments

Check `$ARGUMENTS`:
- `--setup` → jump to Step 1 (force re-run setup even if config exists)
- Empty → proceed to config check

## Step 1: Config Check and First-Run Setup

**Check for config file:**

```bash
cat "$HOME/.config/edge-ic/morning.yaml" 2>/dev/null
```

If the file exists and `--setup` was NOT passed, read it and proceed to Step 2.

If the file does not exist OR `--setup` was passed, run the setup wizard:

**Read the config format reference** from `$PLUGIN_DIR/references/MORNING_CONFIG_FORMAT.md` for field definitions.

**Question 1:** Ask the user:
> "Do you use daily TODO or standup note files?"
- Yes → ask follow-up: "Where are they stored?" (default: `$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md`)
- No → set `daily_notes.enabled: false`

**Question 2:** Ask the user:
> "Which JIRA statuses should surface as 'ready for you'? These are tasks that need your attention."
- Present options: `ON_QE`, `Code Review`, `In Progress`, `POST`
- Allow multi-select
- QA engineers typically pick `ON_QE`; developers might pick `Code Review` or `In Progress`

**Question 3:** Infer GitHub username:

```bash
gh api user --jq '.login' 2>/dev/null || git config user.name 2>/dev/null
```

Ask user to confirm or correct: "Your GitHub username appears to be `{inferred}`. Is that correct?"

**Question 4:** Infer JIRA email from the MCP config environment. Ask user to confirm: "Your JIRA email appears to be `{inferred}`. Is that correct?"

**Question 5:** Auto-discover the board ID. Query boards for the user's projects:

Use `jira_get_agile_boards` to search boards. Present the results and ask the user to pick their primary board. Store the `board_id`.

**Question 6:** Ask the user:
> "Do you track RHEL bug verification? (e.g., TNF resource-agents tickets)"
- Yes → ask for project key (default: `RHEL`), summary filter (default: `[TNF]`), component (default: `resource-agents`)
- No → set `rhel_verification.enabled: false`

**Write the config file:**

```bash
mkdir -p "$HOME/.config/edge-ic"
```

Write the YAML config to `$HOME/.config/edge-ic/morning.yaml` using the collected values. Then proceed to Step 2.

## Usage

```text
/edge-ic:morning           # Run morning briefing (setup on first run)
/edge-ic:morning --setup   # Force re-run setup wizard
```
