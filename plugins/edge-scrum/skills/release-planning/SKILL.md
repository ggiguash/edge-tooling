---
name: release-planning
description: Use when assessing whether the team can deliver planned scope within remaining time — evaluates capacity, timeline, assignment, bug load, sizing, and progress risks per person and per feature to surface planning risks before they become execution problems
allowed-tools: Agent, AskUserQuestion, Write, Read, Glob, Bash, mcp__plugin_mcp-atlassian_mcp-atlassian__jira_get_sprints_from_board, mcp__plugin_mcp-atlassian_mcp-atlassian__jira_search
user-invocable: true
argument-hint: "<version> <sprint-range> bc:<branch-cut> [pd:<pencils-down>] [--component <component>]"
---

# Release Planning Risk Assessment

You are orchestrating a release planning risk assessment for the OCPEDGE team. Data fetching runs inline using MCP tools and transform scripts. Analysis (data-quality gate + 6 checks) is delegated to a sub-agent.

> **Before proceeding**: Read `plugins/edge-scrum/references/Edge-Scrum-Laws.md` to find which law files apply to release planning orchestration. For this skill, load: `laws/00-team-roster.md`, `laws/01-jira-projects.md`, `laws/03-jira-bugs.md`, `laws/04-jira-epics.md`, `laws/05-jira-features.md`, `laws/06-jira-fields.md`, `laws/09-sprint-policies.md`, `laws/14-agent-conventions.md`. The configuration below is derived from the Laws — when in doubt, defer to the law files.

## Configuration

```yaml
# Scrum Board (skill-specific; not in Laws)
board_id: "11479"
board_name: "OpenShift Edge Scrum"
sprint_prefix: ["OCPEDGE Sprint", "OpenShift Edge Sprint"]

# Custom Field IDs (Red Hat Jira instance-specific)
fields:
  story_points:  customfield_10028   # Numeric; Stories/Tasks/Spikes
  epic_link:     customfield_10014   # Story → Epic relationship
  parent_link:   customfield_10018   # Epic → Feature/Initiative relationship
  qa_contact:    customfield_10470   # User picker; QA owner
  flagged:       customfield_10021   # Array; non-empty = impediment
  sme:           customfield_10475   # User picker; Subject Matter Expert

# Component mapping (short name → OCPBUGS components)
components:
  TNA: "Two Node with Arbiter"
  TNF: "Two Node Fencing"
  LVMS: "Logical Volume Manager Storage"
  topolvm: "Logical Volume Manager Storage"
  MicroShift:
    - "MicroShift"
    - "MicroShift / Networking"
    - "MicroShift / Storage"
  SNO: "Installer / Single Node OpenShift"
```

## Execution Model

1. **Steps 0–1**: Load laws/roster, gather release parameters (main context)
2. **Phase 2**: Fetch sprints + features inline using MCP tools → transform scripts (main context)
3. **Phase 3**: Fetch epics + spikes inline using MCP tools → transform scripts (main context)
4. **Phase 4**: Fetch stories + bugs inline using MCP tools → transform scripts (main context)
5. **Phase 5a**: Run `run-checks.py` — deterministic data-quality gate + 6 checks → `checks.json`
6. **Phase 5b**: Delegate narrative to sub-agent — reads `checks.json`, writes `recommendations.json`
7. **Step 6**: Run `assemble-report.py` — produces both `.md` and `.docx` from structured data

**Rules:**

- Data fetching uses MCP tools directly in the main context
- MCP responses are large and get persisted to files automatically — note those file paths
- Transform scripts (`plugins/edge-scrum/bin/`) convert raw MCP data to structured JSON
- Use `check-page.py` to extract pagination info from persisted files
- The analysis sub-agent only needs `Read` and `Write` — it reads `checks.json` and writes `recommendations.json`
- Never embed raw Jira response data in the main context

## User Arguments

The user may provide arguments: `$ARGUMENTS`

- Version number (e.g., `5.0`) → release version
- Sprint range (e.g., `287-292`) → first through last sprint
- Branch cut (e.g., `bc:292` or `branch-cut 292`) → last sprint; the release branch is created after this sprint
- Pencils down (e.g., `pd:291` or `pencils-down 291`) → last sprint where feature code must be merged. If not provided, defaults to same as branch cut
- `--component <name>` → filter to a specific component (TNA, TNF, LVMS, topolvm, MicroShift, SNO)
- No arguments → ask for all required inputs

**Branch cut vs pencils down:** Pencils down is when all feature work must be code-complete. Branch cut is when the release branch is actually created. Feature timeline risk is measured against pencils down (the earlier deadline). Bug fixes can still land between pencils down and branch cut.

---

## Usage Examples

```shell
/release-planning 5.0 287-292 bc:292
/release-planning 5.0 287-292 bc:292 pd:291
/release-planning 5.0 287-292 bc:292 --component TNA
/release-planning
```

## Workflow

### Step 0: Load Edge Scrum Laws and Roster (main context)

Read both files and hold in working memory:

1. Load these law files from `plugins/edge-scrum/references/laws/`:
   - `00-team-roster.md` — team capacity and `.roster.json` structure
   - `01-jira-projects.md` — Jira projects and OCPBUGS components
   - `03-jira-bugs.md` — bug conventions
   - `04-jira-epics.md` — epic conventions and sizing
   - `05-jira-features.md` — feature/initiative conventions and sizing
   - `06-jira-fields.md` — custom field IDs
   - `09-sprint-policies.md` — sprint capacity rules
   - `14-agent-conventions.md` — agent orchestration conventions

2. `plugins/edge-scrum/.roster.json` — extract:
   - **Team roster** — `username`, `display_name`, and `sp_target` per member
   - **Roster size** — count of members
   - If the file does not exist, stop and instruct the user to copy `.roster.json.example` to `.roster.json` and populate it.

The Laws are authoritative. Where this skill and the Laws conflict, the Laws win.

---

### Step 1: Gather Release Parameters (main context)

Parse arguments. Use `AskUserQuestion` for any missing required values:

1. **Release version** — e.g., `5.0`
2. **Sprint range** — first sprint number through last
3. **Branch cut sprint** — which sprint is the last sprint before the release branch is created
4. **Pencils down sprint** — optional; which sprint is the last sprint where feature code must be merged. Defaults to branch cut if not provided
5. **Component filter** — optional, from `--component` argument

Compute and confirm:

- `FIRST` = first sprint number
- `LAST` = last sprint number (branch cut)
- `PENCILS_DOWN` = pencils down sprint number (defaults to `LAST` if not provided)
- `TOTAL_SPRINTS` = LAST − FIRST + 1
- `TOTAL_DEV_SPRINTS` = PENCILS_DOWN − FIRST (sprints available for feature work, excluding refinement sprint)
- `REMAINING_SPRINT_COUNT` = number of remaining sprints until pencils down (not branch cut). After reading `sprints.json`, count how many active + future sprints have sprint numbers ≤ `PENCILS_DOWN`. If pencils down equals branch cut, use `remaining_sprint_count` from `sprints.json` directly.
- `TODAY` = today's date (`YYYY-MM-DD`)
- `COMPONENT_FILTER` = mapped component name from the components table, or `none`

Note: Both `TOTAL_DEV_SPRINTS` and `REMAINING_SPRINT_COUNT` are computed against pencils down, not branch cut. Feature timeline risk is measured against this deadline. The sprints between pencils down and branch cut are available for bug fixes only.

Create the work directory:

```bash
WORKDIR=/tmp/release-planning-$(date +%Y%m%d) && mkdir -p $WORKDIR && echo $WORKDIR
```

Record `WORKDIR` — substitute it into all agent prompts.

---

### Phase 2: Sprint + Feature Collection (inline)

Identical to release-health Phase 2 (standard mode JQL only).

#### 2a — Fetch Sprints

Call `jira_get_sprints_from_board` for board_id `"11479"` three times:

- `state="active"`
- `state="closed"` — paginate using `page_token`; use `limit=50`
- `state="future"`

After all pages are fetched, note all persisted file paths and run:

```bash
python3 plugins/edge-scrum/bin/transform-sprints.py \
  --input <all_persisted_file_paths> \
  --output {WORKDIR}/sprints.json \
  --today {TODAY} \
  --first-sprint {FIRST} \
  --last-sprint {LAST} \
  --total-dev-sprints {TOTAL_DEV_SPRINTS}
```

#### 2b — Fetch Features

Call `jira_search` with:

- **JQL:** `project = OCPSTRAT AND issuetype in (Feature, Initiative) AND labels in ("ocpedge-plan", "microshift") AND "Target Version" = "openshift-{VERSION}" AND (resolution is EMPTY OR resolution not in (Duplicate, Obsolete)) ORDER BY Rank ASC`
- **Fields:** `key, summary, status, issuetype, priority, assignee, fixVersions, labels, description, issuelinks, customfield_10795, customfield_10470, customfield_10473, customfield_10475`
- **limit:** `50`

Paginate using `page_token`. If zero results, use fallback JQL (set `fallback_used`):

```jql
project = OCPSTRAT AND issuetype in (Feature, Initiative) AND labels in ("ocpedge-plan", "microshift") AND "Target Version" = "openshift-{VERSION}" AND status not in (Done, Closed) ORDER BY Rank ASC
```

After all pages fetched, run:

```bash
python3 plugins/edge-scrum/bin/transform-features.py \
  --input <all_persisted_file_paths> \
  --output {WORKDIR}/features.json
```

Append `--fallback-used` if fallback JQL was used.

#### 2c — Verify

Read and check:

- `{WORKDIR}/sprints.json` — if `"error"` key is present or `sprint_map` is empty, warn the user and stop
- `{WORKDIR}/features.json` — if `feature_keys` is empty, warn the user about scope and stop

---

### Phase 3: Epic + Spike Collection (inline)

Identical to release-health Phase 3.

#### 3a — Fetch Epics

Read `{WORKDIR}/features.json`. Extract `feature_keys_csv`.

If `feature_keys` has more than 50 entries, split into batches of 50. For each batch, call `jira_search`:

- **JQL:** `project in (OCPEDGE, USHIFT) AND "Parent Link" in ({feature_keys_batch_csv}) ORDER BY Rank ASC`
- **Fields:** `key, summary, status, assignee, labels, description, parent, customfield_10028, customfield_10018, customfield_10470, customfield_10473, customfield_10475`
- **limit:** `50`

Paginate using `page_token`. After all pages fetched, run:

```bash
python3 plugins/edge-scrum/bin/transform-epics.py \
  --input <all_persisted_file_paths> \
  --output {WORKDIR}/epics.json
```

#### 3b — Fetch Spikes

Read `{WORKDIR}/sprints.json`. Extract `refinement_sprint_id`.

Call `jira_search`:

- **JQL:** `project in (OCPEDGE, USHIFT) AND issuetype = Spike AND sprint = {refinement_sprint_id}`
- **Fields:** `key, summary, status, assignee, issuelinks`
- **limit:** `50`

Paginate using `page_token`. After all pages fetched, run:

```bash
python3 plugins/edge-scrum/bin/transform-spikes.py \
  --input <all_persisted_file_paths> \
  --features-file {WORKDIR}/features.json \
  --epics-file {WORKDIR}/epics.json \
  --sprints-file {WORKDIR}/sprints.json \
  --output {WORKDIR}/spikes.json
```

#### 3c — Verify

Read `{WORKDIR}/epics.json` and verify: `epic_keys` is a non-empty array, `feature_to_epics` is an object, and `epics` is an array. If any check fails, warn the user with a descriptive error and stop.

---

### Phase 4: Story + Bug Collection (inline)

This is the new data collection phase. It fetches story-level data needed for capacity, assignment, and bug load checks.

#### 4a — Fetch Stories Under Epics

Read `{WORKDIR}/epics.json`. Extract `epic_keys`.

Split epic keys into batches of 20. For each batch, call `jira_search`:

- **JQL:** `project in (OCPEDGE, USHIFT, OCPBUGS) AND parent in ({epic_keys_batch_csv}) ORDER BY priority ASC`
- **Fields:** `key, summary, status, issuetype, priority, assignee, labels, updated, parent, customfield_10028, customfield_10021, issuelinks`
- **limit:** `50`

Paginate using `page_token`. After all pages fetched, note all persisted file paths and run:

```bash
python3 plugins/edge-scrum/bin/transform-stories.py \
  --input <all_persisted_file_paths> \
  --output {WORKDIR}/stories.json \
  --today {TODAY}
```

#### 4b — Fetch Unlinked Bugs

Call `jira_search` with:

- **JQL:** `project = OCPBUGS AND component in ("Installer / Single Node OpenShift", "Two Node with Arbiter", "Two Node Fencing", "Logical Volume Manager Storage", "MicroShift", "MicroShift / Networking", "MicroShift / Storage") AND fixVersion in ("{VERSION}", "{VERSION}.0") AND "Epic Link" is EMPTY ORDER BY priority ASC`
- **Fields:** `key, summary, status, priority, assignee, components, labels, updated`
- **limit:** `50`

Paginate using `page_token`. After all pages fetched, run:

```bash
python3 plugins/edge-scrum/bin/transform-bugs.py \
  --input <all_persisted_file_paths> \
  --output {WORKDIR}/bugs.json \
  --today {TODAY}
```

#### 4c — Verify

Read `{WORKDIR}/stories.json` and `{WORKDIR}/bugs.json`. Verify they parse correctly and contain expected top-level keys (`total_stories`, `stories`, `total_bugs`, `bugs`). An empty stories or bugs list is valid (not an error).

---

### Pagination Protocol

This Jira instance uses `page_token` pagination, NOT `start_at`. Follow this protocol for all paginated MCP calls:

1. Make the first call without `page_token`
2. The response may be persisted to a file. Note the file path.
3. Run `check-page.py` to get pagination info:

   ```bash
   python3 plugins/edge-scrum/bin/check-page.py <persisted_file_path>
   ```

   Output: `{"issues_count": N, "has_more": bool, "next_page_token": "..."}`
4. If `has_more` is `true`: make the next call with `page_token` set to the `next_page_token` value. Repeat from step 2.
5. If `has_more` is `false`: pagination is complete.

For small responses that fit in context (not persisted), write them to `{WORKDIR}/raw_<type>_<page>.json` using `Write`, then run `check-page.py` on that file.

---

### Phase 5a: Run Checks (deterministic)

Run the planning risk checks script. This performs the data-quality gate and all 6 checks deterministically — no LLM needed:

```bash
python3 plugins/edge-scrum/bin/run-checks.py \
  --features {WORKDIR}/features.json \
  --epics {WORKDIR}/epics.json \
  --stories {WORKDIR}/stories.json \
  --bugs {WORKDIR}/bugs.json \
  --roster plugins/edge-scrum/.roster.json \
  --remaining-sprints {REMAINING_SPRINT_COUNT} \
  --component-filter "{COMPONENT_FILTER}" \
  --output {WORKDIR}/checks.json
```

Verify `{WORKDIR}/checks.json` was written and contains a `meta` key.

### Phase 5b: Recommendations (sub-agent)

Read `plugins/edge-scrum/skills/release-planning-analysis/SKILL.md`. Substitute `{WORKDIR}` and `{VERSION}`, then spawn as a sub-agent.

This agent reads `checks.json` (pre-computed numbers) and writes `{WORKDIR}/recommendations.json` with narrative recommendations. It does NOT compute any numbers — only interprets and advises.

Verify `{WORKDIR}/recommendations.json` was written and contains `executive_summary`.

---

### Step 6: Assemble Report (main context)

Run the report assembly script. This renders both markdown and DOCX from structured data — no markdown parsing needed:

```bash
python3 plugins/edge-scrum/bin/assemble-report.py \
  --checks {WORKDIR}/checks.json \
  --recommendations {WORKDIR}/recommendations.json \
  --template plugins/edge-scrum/references/release-planning-report-template.md \
  --version {VERSION} \
  --today {TODAY} \
  --first-sprint {FIRST} \
  --last-sprint {LAST} \
  --pencils-down {PENCILS_DOWN} \
  --remaining-sprints {REMAINING_SPRINT_COUNT} \
  --total-dev-sprints {TOTAL_DEV_SPRINTS} \
  --output .reports/release_planning_{VERSION}_{TODAY}
```

This produces both `.reports/release_planning_{VERSION}_{TODAY}.md` and `.reports/release_planning_{VERSION}_{TODAY}.docx` with styled tables, risk-level coloring, and Jira hyperlinks.

Clean up: `test -n "{WORKDIR}" && [[ "{WORKDIR}" == /tmp/release-planning-* ]] && rm -rf -- "{WORKDIR}"`

---

## Edge Cases

- **No Features found**: Try fallback JQL (handled in Phase 2b); warn user to confirm scope; stop if still empty.
- **Feature with no Epics**: Flagged by data-quality gate as FAIL — "no epics created."
- **Epic with no Stories**: Flagged by data-quality gate as FAIL — "epic has no stories."
- **Component filter matches no features**: Warn user and exit cleanly — "No features found for component {COMPONENT_FILTER}."
- **stories.json empty**: Data-quality gate flags all features as FAIL — no numeric projections possible.
- **bugs.json empty**: Bug load check reports no issues — not an error.
- **Sprint data unavailable**: transform-sprints.py sets `"error"` in JSON; main context stops before Phase 3.
- **Version format varies** (`5.0` vs `5.0.0`): Bug JQL tries both `fixVersion in ("{VERSION}", "{VERSION}.0")`.
- **Unlinked bugs (no epic)**: Collected in Phase 4b, reported separately in Bug Load check.

---

## Important Notes

- **Read-only**: This skill does not modify any Jira data.
- **Transform scripts**: `plugins/edge-scrum/bin/` — reusable data transformation (no LLM needed)
- **Analysis sub-agent**: `plugins/edge-scrum/skills/release-planning-analysis/SKILL.md` — LLM-driven risk assessment
- **Work directory**: `{WORKDIR}` persists across phases within a run. Rerunning on the same day overwrites prior files.
- **Laws files**: Authoritative for all team conventions. Never hardcode roster, rules, or sizing in skill definitions.
- **Data-quality gate**: MUST run before capacity and timeline checks. Features without story-level breakdown are excluded from numeric projections.
