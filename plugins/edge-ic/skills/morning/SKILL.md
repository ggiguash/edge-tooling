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

If the file exists and `--setup` was NOT passed, read it and proceed to Step 2. If YAML parsing fails, warn the user and offer to re-run setup (`/morning --setup`), then stop.

If the file does not exist OR `--setup` was passed, run the setup wizard:

**Read the config format reference** from `$PLUGIN_DIR/references/MORNING_CONFIG_FORMAT.md` for field definitions.

**Question 1:** Ask the user:
> "Do you use daily TODO or standup note files?"

- Yes → ask follow-up: "Where are they stored?" (default: `$HOME/.daily/{YYYY}/{MM}/{YYYY-MM-DD}.md`)
  - **Validate immediately:** resolve the path template for today and yesterday, then check if either file (or the parent directory) exists. If nothing is found, warn the user: "No files found at that path — double-check and try again?" Allow them to correct or confirm.
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

**Question 4:** Auto-discover boards. Query boards for the user's projects:

Use `jira_get_agile_boards` to search boards. Present the results and ask the user to pick one or more boards they want to track sprints from. Store the selected IDs in `board_ids` (list).

Follow-up: "Do you want to add boards from other projects?" If yes, ask for the project key, search its boards, and let them pick. Repeat until they're done.

**Question 5:** Ask the user:
> "Do you want to track QA tasks (tickets where you are the QA Contact)?"

- Yes → ask two follow-ups:
  - "Which statuses mean a ticket is ready for your QA work? (comma-separated)" — default: `ON_QA`. This is a free-text field since different projects use different workflows (e.g., OCPBUGS uses `ON_QA`, other projects may use `Code Review` or `Review`).
  - "Which Jira projects should be searched for QA tasks? (comma-separated project keys)" — default: `OCPBUGS, OCPEDGE`. Store as `jira.qa_projects`.
  - "Filter by specific components? Enter component names comma-separated, or leave blank for all." (e.g., `Two Node Fencing, LVMS`; default: empty = no filter)
- No → set `sections.qa_tasks: false`

**Question 6:** Ask the user:
> "Do you want to see PRs assigned to you for review? (useful for cherrypick PRs and code reviews)"

- Yes → set `sections.review_queue: true`
- No → set `sections.review_queue: false`

**Question 7:** Ask the user:
> "Do you track RHEL bug verification? (e.g., TNF resource-agents tickets)"

- Yes → ask for project key (default: `RHEL`), summary filter (default: `[TNF]`), component (default: `resource-agents`)
- No → set `rhel_verification.enabled: false`

**Question 8:** Ask the user:
> "What title do you want in the banner? (default: `Morning Edge`)"

- Accept a custom title (any text, 1-3 words recommended)
- Default: `Morning Edge`

**Write the config file:**

```bash
mkdir -p "$HOME/.config/edge-ic"
```

Write the YAML config to `$HOME/.config/edge-ic/morning.yaml` using the collected values. Then proceed to Step 2.

Steps 2-8 are fully independent. **Issue all their tool calls in a single response turn so they execute in parallel** — do not wait for one step to finish before starting the next. In Claude Code this means batching all MCP and Bash calls together. Only render output (Step 10) after all steps complete. Skip any step whose corresponding section is disabled in config.

## Step 2: Gather QA Tasks

Skip if `sections.qa_tasks` is `false` in config.

**If any JIRA MCP call fails in this step**, skip QA tasks and record an error note: "Could not reach JIRA — QA tasks skipped." Note: `currentUser()` in JQL only works when the MCP session is authenticated with the correct email; if queries return empty unexpectedly, verify JIRA auth.

Run **two JQL queries** to separate assigned vs. unassigned QA tickets:

**Query 1 — Your QA** (tickets assigned to you):

```text
jira_search with JQL: "QA Contact" = currentUser() AND status in ("{status1}", "{status2}") AND project in ({proj1}, {proj2}, ...) ORDER BY priority DESC
```

Use `fields: "status,assignee,issuetype,summary,priority,components"` and `limit: 20`.

**Query 2 — Unassigned QA** (only if `jira.qa_components` is set in config — skip otherwise to avoid returning hundreds of irrelevant tickets):

```text
jira_search with JQL: "QA Contact" is EMPTY AND status in ("{status1}", "{status2}") AND project in ({proj1}, {proj2}, ...) AND component in ("{comp1}", "{comp2}") ORDER BY priority DESC
```

Use `fields: "status,assignee,issuetype,summary,priority,components"` and `limit: 10`.

If `jira.qa_components` is NOT set, skip Query 2 and add a note in the output: "Configure `qa_components` in `~/.config/edge-ic/morning.yaml` to see unassigned QA tickets for your team."

Replace `{proj1}`, `{proj2}` etc. with values from `jira.qa_projects` in config (default: `["OCPBUGS", "OCPEDGE"]`). Replace `{status1}`, `{status2}` etc. with values from `jira.qa_statuses` in config (default: `["ON_QA"]`). Before interpolating any config value into JQL, escape backslashes as `\\` and double-quotes as `\"` to prevent query breakage.

**Note:** The QA Contact field is `customfield_10470` (user picker). The JQL clause name is `"QA Contact"`. This is separate from the `assignee` field — a ticket's assignee is the developer; the QA Contact is the person responsible for testing. The `ON_QA` status exists on projects like OCPBUGS and CNV but not on OCPEDGE/USHIFT, so this query searches cross-project.

Skip the per-ticket comment scan by default — set `requester: null` for all results. Only scan comments if there are 3 or fewer QA tickets (to avoid serial roundtrips slowing the briefing). When scanning, fetch all tickets in parallel using `jira_get_issue` with `comment_limit: 2`, checking for keywords: "ready for QA", "please test", "QA needed", "please verify".

Store results as a list of:

- `key`: ticket key (e.g., `OCPEDGE-2710`)
- `summary`: ticket summary
- `status`: ticket status
- `requester`: comment author who requested QA (or null)
- `link`: `https://redhat.atlassian.net/browse/{key}`
- `qa_assigned`: `true` if QA Contact = currentUser(), `false` if QA Contact is EMPTY

## Step 3: Gather Sprint Backlog

Skip if `sections.sprint_backlog` is `false` in config.

**If any JIRA MCP call fails in this step**, skip sprint backlog and record an error note: "Could not reach JIRA — sprint backlog skipped."

**Board IDs:** If `board_ids` is missing or empty in config, attempt auto-discovery via `jira_get_agile_boards`. If that fails too, skip sprint section. If config has a legacy `board_id` (string) instead of `board_ids` (list), treat it as a single-element list.

**Fetch all active sprint issues in a single JQL query** (eliminates per-board sprint discovery calls):

```text
jira_search with JQL: assignee = currentUser() AND sprint in openSprints() ORDER BY status ASC, priority DESC
```

Use `fields: "status,assignee,issuetype,summary,priority,customfield_10028,customfield_10016,sprint"` and `limit: 50`.

**Extract sprint metadata from the results:** The `sprint` field on each issue contains the sprint name, start date, end date, and board. Group issues by sprint name and derive:

- Sprint name, start date, end date from the sprint field
- Days remaining = sprint end date minus today
- Total sprint days = sprint end date minus sprint start date
- Sprint is urgent if days remaining <= 3

If the query returns no results, skip the sprint section silently. If the `sprint` field is unavailable or null on any issue, fall back to `jira_get_sprints_from_board` for the configured board IDs.

**Note:** Story points are typically in `customfield_10028` ("Story Points"). Fall back to `customfield_10016` ("Story point estimate") if `customfield_10028` is null. If neither has data, show "Story Points: N/A".

**Compute** (per sprint):

- Separate into: completed (status category = Done) and not-done (everything else)
- Sum story points: try `customfield_10028` ("Story Points") first, then `customfield_10016` ("Story point estimate"). If neither has data, show "Story Points: N/A" in the sprint header
- Group not-done issues by status in workflow order: In Progress, Code Review, POST, To Do, New

Store results as a list of sprints, each with:

- `sprint_name`: e.g., "Sprint 26"
- `board_name`: e.g., "OpenShift Edge Scrum"
- `days_remaining`: integer
- `total_days`: integer
- `points_completed`: integer
- `points_total`: integer
- `is_urgent`: boolean (days_remaining <= 3)
- `issues`: list grouped by status, each with key, summary, status, link

**Rendering:** If multiple boards have active sprints, render a separate sprint header and backlog section for each. Show the board name in the header to distinguish them.

## Step 4: Gather Yesterday's Carry-Over

Skip if `sections.carry_over` is `false` in config or `daily_notes.enabled` is `false`.

**Determine yesterday's workday:**

```bash
if date -v-1d +%Y-%m-%d >/dev/null 2>&1; then
  # macOS/BSD
  if [ "$(date +%u)" -eq 1 ]; then
    yesterday=$(date -v-3d +%Y-%m-%d)
  else
    yesterday=$(date -v-1d +%Y-%m-%d)
  fi
else
  # Linux/GNU
  if [ "$(date +%u)" -eq 1 ]; then
    yesterday=$(date -d "3 days ago" +%Y-%m-%d)
  else
    yesterday=$(date -d "yesterday" +%Y-%m-%d)
  fi
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

- File contains `* TODO` or `** TODO` or `SCHEDULED:` → org-mode format
- File contains `## Priority` or `## In Progress` or `- [ ]` → TODO format
- Otherwise → freeform format

**Org-mode format:** Extract all headings with a `TODO` keyword (not `DONE`):

- Lines matching `^\*+ TODO (.*)` → extract the heading text after `TODO`
- Lines matching `^\*+ IN-PROGRESS (.*)` or `^\*+ NEXT (.*)` → also extract as incomplete
- Ignore headings with `DONE`, `CANCELLED`, or `WAITING` keywords
- If a `TODO` heading has a `SCHEDULED: <YYYY-MM-DD>` line beneath it, include the date in the carry-over item

**TODO format:** Extract all unchecked items (`- [ ]`) from all sections. These are incomplete tasks.

**Freeform format:** Extract lines that:

- Start with `in-progress` or `in progress` (case-insensitive)
- Do NOT start with `done`, `completed`, `finished`, `verified` (case-insensitive)

Store results as a list of raw text strings.

## Step 5: Gather Open PRs

Skip if `sections.open_prs` is `false` in config.

**Fetch open PRs directly via `gh`** (primary source — always up to date):

```bash
gh search prs --author=@me --state=open --json repository,number,title,createdAt,url --limit 50
```

Compute `days_open` from `createdAt` (today's date minus `createdAt` in days — be precise, do not eyeball). **Discard any PR where `days_open` > 200** — these are stale/abandoned PRs that add noise. Set `days_idle` and `missing_labels` to "?" (the CI dashboard is no longer fetched). If `gh` is not available, skip this section with a note.

**Skip the per-PR review thread fetch entirely** — it adds N sequential round-trips and the briefing doesn't need it. Set `unresolved: null` for all PRs. The PR link is enough to check threads on demand.

Store results as a list of:

- `repo`: e.g., `openshift/origin`
- `pr_number`: integer
- `title`: string
- `days_open`: string (e.g., "12d")
- `link`: full GitHub PR URL

## Step 6: Gather PRs Awaiting Your Review

Skip if `sections.review_queue` is `false` in config.

**Fetch PRs where the user is a requested reviewer:**

```bash
gh search prs --review-requested=@me --state=open --json repository,number,title,createdAt,url --limit 20
```

If `gh` is not available or the command fails, skip this section with a note: "Could not fetch review queue — skipping."

**Filter out stale PRs:** Discard any PR where `createdAt` is older than 200 days. This avoids surfacing abandoned review requests from old projects.

**For each remaining PR**, compute:

- `days_open`: days since `createdAt`
- `repo`: repository full name (e.g., `openshift/origin`)

Store results as a list of:

- `repo`: e.g., `openshift/origin`
- `pr_number`: integer
- `title`: string
- `days_open`: string (e.g., "5d")
- `link`: full GitHub PR URL

## Step 7: Check Quarterly Reminders

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
if date -j -f "%Y-%m-%d" "$quarter_end" +%s >/dev/null 2>&1; then
  # macOS/BSD
  days_left=$(( ( $(date -j -f "%Y-%m-%d" "$quarter_end" +%s) - $(date +%s) ) / 86400 ))
else
  # Linux/GNU
  days_left=$(( ( $(date -d "$quarter_end" +%s) - $(date +%s) ) / 86400 ))
fi
echo "$quarter_end $days_left"
```

If `days_left <= 14`, store a reminder with:

- `quarter_end_date`: formatted date (e.g., "Jun 30")
- `days_left`: integer
- Two action items:
  - "Complete Quarterly Connection in Workday"
  - "Submit RewardZone points: https://rewardzone.redhat.com/"

## Step 8: Check RHEL Verification Queue

Skip if `sections.rhel_queue` is `false` in config or `rhel_verification.enabled` is `false`.

**If the JIRA MCP call fails**, skip this section and record an error note: "Could not reach JIRA — RHEL queue skipped." The `"Preliminary Testing" = Requested` clause uses a custom field that works on Jira Cloud; if the query fails with a field-not-found error, log it and skip.

Query JIRA:

```text
jira_search with JQL: project = "{rhel_verification.project}" AND summary ~ "{rhel_verification.summary_filter}" AND component = "{rhel_verification.component}" AND "Preliminary Testing" = Requested AND "Test Coverage" is EMPTY AND (fixVersion in unreleasedVersions() OR fixVersion is EMPTY)
```

Before interpolating `rhel_verification.*` config values, escape backslashes as `\\` and double-quotes as `\"`.

Use `fields: "summary,status,fixVersions"` and `limit: 20`.

Store results as:

- `count`: number of tickets found
- `tickets`: list of key + summary

## Step 9: Deduplicate

Before rendering, remove duplicate tickets across sections. A ticket that appears in multiple data sources is shown only in the highest-priority section.

**Priority order** (highest first):

1. QA Ready (Step 2)
2. Sprint Backlog (Step 3)
3. Carry-over (Step 4)
4. RHEL Queue (Step 8)

For each ticket key found in a higher-priority section, remove it from all lower-priority sections. Carry-over items are matched by JIRA key if they contain one (e.g., a line like `OCPEDGE-2700: some task` matches key `OCPEDGE-2700`).

## Step 10: Render Output

**Do NOT read the output format reference file.** All rendering rules are inline below for speed.

**Title banner** — copy-paste the pre-rendered default title verbatim (do not compute it):

```text
              █▄ ▄█ █▀▀█ █▀▀▄ █▄ █ █ █▄ █ █▀▀▀
              █ ▀ █ █  █ █▄▄▀ █ ▀█ █ █ ▀█ █ ▀█
              ▀   ▀ ▀▀▀▀ ▀  ▀ ▀  ▀ ▀ ▀  ▀ ▀▀▀▀
              █▀▀▀ █▀▀▄ █▀▀▀ █▀▀▀
              █▀▀  █  █ █ ▀█ █▀▀
              ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀
```

If the user configured a custom title, fall back to spaced capital letters (e.g., `D A I L Y`). Do not attempt pixel rendering for custom titles.

**All panels** use `╭╮╰╯│─` box-drawing, 60 chars wide. Section header: `╭─ » {title} ─...─╮`. Skip empty sections.

**Header panel:**

```text
╭──────────────────────────────────────────────────────────╮
│  ☀  Morning Briefing — {date}                            │
│  **{sprint}** — {days_left}/{total} days · {pts_done}/{pts_total} SP
│  ▐{bar}▌ {pct}%                                          │
│  > {summary}                                             │
╰──────────────────────────────────────────────────────────╯
```

Progress bar: 10 slots, filled by story points ratio. Positions 1-3: 🟥, 4-5: 🟠, 6-7: 🟡, 8-10: 🟢, unfilled: `░`. Omit bar if story points N/A.

**Section order:** QA Ready, Sprint Backlog, Carry-over, Open PRs, Review Queue, RHEL Queue, Reminders.

**QA Ready panel** — split into two sub-groups:

- `▸ Your QA` (`qa_assigned: true`) — tickets where you are the QA Contact
- `▸ Unassigned` (`qa_assigned: false`) — no QA Contact set

Omit a sub-group if empty. Skip panel if both empty.

**Formatting rules:**

- Ticket keys: **bold** (`**KEY**`)
- JIRA links: `https://redhat.atlassian.net/browse/{KEY}`
- Sprint name: always **bold**
- URLs may extend past the right `│`

**Reminders:** Sprint urgency if days_remaining <= 3 (⚠ or 🔴 if last day). Quarterly reminder if within 14 days.

**All empty:** "Nothing on your plate — enjoy the quiet morning"

**Errors:** Append `╭─ ⚠ Notes ─...╮` panel with `⚠` per failed source.

## Usage

```text
/edge-ic:morning           # Run morning briefing (setup on first run)
/edge-ic:morning --setup   # Force re-run setup wizard
```
