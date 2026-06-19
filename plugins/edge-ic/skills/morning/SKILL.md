---
name: edge-ic:morning
description: Surface your daily task list — QA-ready tickets, sprint backlog, carry-over items, open PRs, RHEL verification queue, and quarterly reminders. Use at the start of your day to see what needs attention.
allowed-tools:
  - Read
  - Write
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

Aggregate your daily task surface from JIRA, daily notes, PR dashboards, and date-based reminders into a single prioritized morning briefing.

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

**Question 2:** Infer GitHub username:

```bash
gh api user --jq '.login' 2>/dev/null || git config user.name 2>/dev/null
```

Ask user to confirm or correct: "Your GitHub username appears to be `{inferred}`. Is that correct?"

**Question 3:** Infer JIRA email from the MCP config environment:

```bash
echo "${JIRA_USERNAME:-}" 2>/dev/null
```

Ask user to confirm: "Your JIRA email appears to be `{inferred}`. Is that correct?"

**Question 4:** Auto-discover the board ID. Query boards for the user's projects:

Use `jira_get_agile_boards` to search boards. Present the results and ask the user to pick their primary board. Store the `board_id`.

**Question 5:** Ask the user:
> "Do you track RHEL bug verification? (e.g., TNF resource-agents tickets)"
- Yes → ask for project key (default: `RHEL`), summary filter (default: `[TNF]`), component (default: `resource-agents`)
- No → set `rhel_verification.enabled: false`

**Write the config file:**

```bash
mkdir -p "$HOME/.config/edge-ic"
```

Write the YAML config to `$HOME/.config/edge-ic/morning.yaml` using the collected values. Then proceed to Step 2.

Steps 2-7 are independent and can be run in parallel. Skip any step whose corresponding section is disabled in config.

## Step 2: Gather QA Tasks

Skip if `sections.qa_tasks` is `false` in config.

Query JIRA for tickets where the current user is the **QA Contact** and status indicates QA is needed:

```
jira_search with JQL: "QA Contact" = currentUser() AND status = "ON_QE" ORDER BY priority DESC
```

Use `fields: "status,assignee,issuetype,summary,priority"` and `limit: 50`.

**Note:** The QA Contact field is `customfield_10470` (user picker). The JQL clause name is `"QA Contact"`. This is separate from the `assignee` field — a ticket's assignee is the developer; the QA Contact is the person responsible for testing.

For each result, fetch its details using `jira_get_issue` with `comment_limit: 2` to scan the last 2 comments for QA request keywords: "ready for QA", "please test", "QA needed", "please verify". If found, note the comment author as the requester.

Store results as a list of:
- `key`: ticket key (e.g., `OCPEDGE-2710`)
- `summary`: ticket summary
- `status`: ticket status
- `requester`: comment author who requested QA (or null)
- `link`: `https://redhat.atlassian.net/browse/{key}`

## Step 3: Gather Sprint Backlog

Skip if `sections.sprint_backlog` is `false` in config.

**Discover active sprint:**

Use `jira_get_sprints_from_board` with `board_id` from config and `state: "active"`. Extract:
- Sprint name
- Sprint start date
- Sprint end date
- Sprint ID

**Calculate sprint metadata:**
- Days remaining = sprint end date minus today
- Total sprint days = sprint end date minus sprint start date
- Sprint is urgent if days remaining <= 3

**Fetch the user's sprint issues via JQL** (avoids pagination issues with large boards):

```
jira_search with JQL: assignee = currentUser() AND sprint = {sprint_id} ORDER BY status ASC, priority DESC
```

Use `fields: "status,assignee,issuetype,summary,priority,customfield_10028,customfield_10016"` and `limit: 50`.

**Note:** Story points are typically in `customfield_10028` ("Story Points"). Fall back to `customfield_10016` ("Story point estimate") if `customfield_10028` is null. If neither has data, show "Story Points: N/A".

**Compute:**
- Separate into: completed (status category = Done) and not-done (everything else)
- Sum story points: completed points vs total points
- Group not-done issues by status in workflow order: In Progress, Code Review, POST, To Do, New

Store results as:
- `sprint_name`: e.g., "Sprint 26"
- `days_remaining`: integer
- `total_days`: integer
- `points_completed`: integer
- `points_total`: integer
- `is_urgent`: boolean (days_remaining <= 3)
- `issues`: list grouped by status, each with key, summary, status, link

## Step 4: Gather Yesterday's Carry-Over

Skip if `sections.carry_over` is `false` in config or `daily_notes.enabled` is `false`.

**Determine yesterday's workday:**

```bash
if [ "$(date +%u)" -eq 1 ]; then
  # Monday — look back to Friday
  yesterday=$(date -v-3d +%Y-%m-%d)
else
  yesterday=$(date -v-1d +%Y-%m-%d)
fi
echo "$yesterday"
```

**Resolve the file path** by replacing placeholders in `daily_notes.path`:
- `{YYYY}` → year from yesterday
- `{MM}` → month from yesterday (zero-padded)
- `{DD}` → day from yesterday (zero-padded)
- `{YYYY-MM-DD}` → full date

**Read the file.** If it does not exist, skip this section silently (no warning).

**Parse based on format:**

If `daily_notes.format` is `auto`, detect:
- File contains `## Priority` or `## In Progress` or `- [ ]` → TODO format
- Otherwise → freeform format

**TODO format:** Extract all unchecked items (`- [ ]`) from all sections. These are incomplete tasks.

**Freeform format:** Extract lines that:
- Start with `in-progress` or `in progress` (case-insensitive)
- Do NOT start with `done`, `completed`, `finished`, `verified` (case-insensitive)

Store results as a list of raw text strings.

## Step 5: Gather Open PRs

Skip if `sections.open_prs` is `false` in config.

**Fetch the latest run ID:**

```bash
curl -sf "https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results/logs/periodic-ci-openshift-eng-edge-tooling-main-pr-notifier/latest-build.txt"
```

If this fails, skip this section with a note: "Could not fetch PR dashboard — skipping open PRs section."

**Fetch the PR summary page:**

Use WebFetch on:
```
https://gcsweb-ci.apps.ci.l2s4.p1.openshiftapps.com/gcs/test-platform-results/logs/periodic-ci-openshift-eng-edge-tooling-main-pr-notifier/{run_id}/artifacts/pr-notifier/openshift-edge-tooling-gh-notifier/artifacts/edge-tooling-pr-summary.html
```

With prompt: "Extract all PRs where the Author column matches '{config.github.username}'. For each PR return: repo (e.g. openshift/origin), PR number, title, days open, days idle, missing labels."

Store results as a list of:
- `repo`: e.g., `openshift/origin`
- `pr_number`: integer
- `title`: string
- `days_open`: string (e.g., "12d")
- `days_idle`: string (e.g., "2d")
- `missing_labels`: string (e.g., "lgtm")
- `link`: full GitHub PR URL

## Step 6: Check Quarterly Reminders

Skip if `sections.quarterly_reminders` is `false` in config.

**Determine quarter end date:**

```bash
month=$(date +%-m)
year=$(date +%Y)
if [ "$month" -le 3 ]; then
  quarter_end="${year}-03-31"
elif [ "$month" -le 6 ]; then
  quarter_end="${year}-06-30"
elif [ "$month" -le 9 ]; then
  quarter_end="${year}-09-30"
else
  quarter_end="${year}-12-31"
fi
days_left=$(( ( $(date -j -f "%Y-%m-%d" "$quarter_end" +%s) - $(date +%s) ) / 86400 ))
echo "$quarter_end $days_left"
```

If `days_left <= 14`, store a reminder with:
- `quarter_end_date`: formatted date (e.g., "Jun 30")
- `days_left`: integer
- Two action items:
  - "Complete Quarterly Connection in Workday"
  - "Submit RewardZone points: https://rewardzone.redhat.com/"

## Step 7: Check RHEL Verification Queue

Skip if `sections.rhel_queue` is `false` in config or `rhel_verification.enabled` is `false`.

Query JIRA:

```
jira_search with JQL: project = "{rhel_verification.project}" AND summary ~ "{rhel_verification.summary_filter}" AND component = "{rhel_verification.component}" AND "Preliminary Testing" = Requested AND "Test Coverage" is EMPTY AND (fixVersion in unreleasedVersions() OR fixVersion is EMPTY)
```

Use `fields: "summary,status,fixVersions"` and `limit: 20`.

Store results as:
- `count`: number of tickets found
- `tickets`: list of key + summary

## Step 8: Deduplicate

Before rendering, remove duplicate tickets across sections. A ticket that appears in multiple data sources is shown only in the highest-priority section.

**Priority order** (highest first):
1. QA Ready (Step 2)
2. Sprint Backlog (Step 3)
3. Carry-over (Step 4)
4. RHEL Queue (Step 7)

For each ticket key found in a higher-priority section, remove it from all lower-priority sections. Carry-over items are matched by JIRA key if they contain one (e.g., a line like `OCPEDGE-2700: some task` matches key `OCPEDGE-2700`).

## Step 9: Render Output

Read the output format reference from `$PLUGIN_DIR/references/MORNING_OUTPUT_FORMAT.md`.

**Render the sprint header** (always shown if sprint data is available):
- Sprint name, days remaining of total days
- Story points completed vs total with percentage
- Progress bar: 20 chars, filled proportionally with `█` and `░`

**Render the summary line:**
- Count items in each non-empty section
- Join with ` · ` separator
- Append `⚠ quarterly reminder` if quarterly reminder is active
- Append `⚠ sprint ending soon` if sprint is urgent (days_remaining <= 3)

**Render each section** in order: QA Ready, Sprint Backlog, Carry-over, Open PRs, RHEL Queue, Reminders.
- Skip any section that has zero items
- Use the exact formatting from the output format reference
- All JIRA links: `https://redhat.atlassian.net/browse/{KEY}`

**Reminders section** collects:
- Sprint urgency reminder (if days_remaining <= 3): "⚠ {sprint_name} ends in {N} days — prepare tasks for next sprint" (or "🔴 {sprint_name} ends today — finalize work and groom next sprint")
- Quarterly reminder (if within 14 days of quarter end)

**If all sections are empty** (no QA tasks, no sprint items, no carry-over, no PRs, no RHEL tickets, no reminders), output:

```
☀ Morning Briefing — {date}

  Nothing on your plate — enjoy the quiet morning
```

**Error notes:** If any data source failed during gathering, append a note at the bottom:

```
──────────────────────────────────────────────────────────
⚠ Could not reach JIRA — QA tasks, sprint backlog, and RHEL queue skipped
⚠ Could not fetch PR dashboard — open PRs section skipped
```

## Edge Cases

- **No active sprint:** If `jira_get_sprints_from_board` returns no active sprint, skip the sprint header and sprint backlog section entirely. Show a note in the output: "No active sprint found."
- **JIRA MCP unavailable:** If any JIRA MCP call fails, skip all JIRA-dependent sections (QA tasks, sprint backlog, RHEL queue). Append error note at bottom.
- **PR dashboard unavailable:** If `latest-build.txt` fetch or the HTML fetch fails, skip the open PRs section. Append error note.
- **No daily notes file:** Skip carry-over silently — no warning, no empty section.
- **Monday carry-over:** Look back to Friday (3 days) for carry-over, not Saturday/Sunday.
- **Config file exists but is malformed:** If YAML parsing fails, warn user and offer to re-run setup (`/morning --setup`).
- **Story points field varies:** Try `customfield_10028` ("Story Points") first, then `customfield_10016` ("Story point estimate"). If neither has data, show "Story Points: N/A" in sprint header.
- **Board ID not set in config:** If `board_id` is missing, attempt auto-discovery via `jira_get_agile_boards`. If that fails, skip sprint section.

## Gotchas

- **`currentUser()` in JQL:** Works only when authenticated via MCP. If the MCP config uses a different email than expected, queries return nothing. Verify during setup (Question 4).
- **PR dashboard run ID:** The `latest-build.txt` file contains just the numeric run ID with no trailing newline. Strip whitespace before constructing the URL.
- **RHEL "Preliminary Testing" field:** This is a custom field. The JQL syntax `"Preliminary Testing" = Requested` works on Jira Cloud but the field ID may vary by project. If the query fails, log the error and skip.
- **macOS vs Linux date commands:** The `date -v-3d` syntax is macOS-specific. For portability, use: `date -d "3 days ago"` on Linux. Detect platform first:

```bash
if date -v-1d +%Y-%m-%d 2>/dev/null; then
  # macOS
  yesterday=$(date -v-1d +%Y-%m-%d)
else
  # Linux
  yesterday=$(date -d "yesterday" +%Y-%m-%d)
fi
```

## Usage

```text
/edge-ic:morning           # Run morning briefing (setup on first run)
/edge-ic:morning --setup   # Force re-run setup wizard
```
