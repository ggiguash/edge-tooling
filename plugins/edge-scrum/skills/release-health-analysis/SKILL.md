---
name: release-health-analysis
description: Analyze release health data and produce assessment
allowed-tools: Read, Write, Bash, mcp__plugin_mcp-atlassian_mcp-atlassian__jira_search
user-invocable: false
---

# release-health: Analysis

## Purpose

Perform the full hierarchy analysis, risk assessment, and generate all report sections, writing the results to `analysis.md` in the work directory.

## When to Spawn

The parent release-health skill spawns this agent during Phase 4, after Phase 3 (Epic Fetcher + Spike Finder) completes. This is the only Phase 4 agent.

## Capabilities

- Jira MCP search queries (`jira_search`)
- File reading via `Read` tool (all four phase data files + Edge Scrum Laws + `.roster.json`)
- JSON file writing via `Write` tool

This agent does **not** modify any Jira data.

## Parameters

Substituted by the parent before spawning:

| Placeholder | Description |
|---|---|
| `{WORKDIR}` | Work directory path |
| `{VERSION}` | OCP release version (e.g., `4.19`, `5.0`) |
| `{TODAY}` | Today's date in `YYYY-MM-DD` format |
| `{REFINEMENT_SPRINT_NUM}` | Sprint number of the refinement sprint |

## Instructions

### 1. Read Context Files

1. `plugins/edge-scrum/.roster.json`
   Extract: `members` array — use `username` for ownership matching, `sp_target` per member for capacity.
   Derive `roster_size` (count of members) and `total_sp_per_sprint` (sum of all `sp_target` values).
   If a member is missing `sp_target`, default that member to 8. If the file is absent, halt with an error.
2. Load these law files from `plugins/edge-scrum/references/laws/`:
   - `07-workflow-states.md` — done states per issue type
   - `02-jira-stories.md` — bugs-always-zero-SP rule and story pointing
   - `04-jira-epics.md` — epic sizing scales
   - `05-jira-features.md` — feature/initiative sizing scales
   - `01-jira-projects.md` — OCPBUGS components
   - `06-jira-fields.md` — custom field IDs
3. `{WORKDIR}/sprints.json`
4. `{WORKDIR}/features.json`
5. `{WORKDIR}/epics.json`
6. `{WORKDIR}/spikes.json`

---

### 2. Fetch Child Issues

Split `epic_keys_csv` from `epics.json` into batches of ~20. For each batch, paginate with `page_token`, `limit=50` until all results are fetched:

```jql
project in (OCPEDGE, USHIFT, OCPBUGS) AND "Epic Link" in ({batch_csv}) ORDER BY priority ASC
```

Also fetch unlinked OCPBUGS bugs (use components from Laws). Paginate with `page_token`, `limit=50` until all results are fetched:

```jql
project = OCPBUGS
  AND component in ("Installer / Single Node OpenShift", "Two Node with Arbiter", "Two Node Fencing", "Logical Volume Manager Storage")
  AND fixVersion in ("{VERSION}", "{VERSION}.0")
  AND "Epic Link" is EMPTY
ORDER BY priority ASC
```

Fields per issue:

```text
key, summary, status, issuetype, priority, assignee, sprint, labels, updated,
customfield_10028, customfield_10470, customfield_10021, customfield_10014, issuelinks
```

Per issue, compute:

- `sp`: `customfield_10028` — **ALWAYS 0 for any Bug issuetype, no exceptions**
- `epic_key`: `customfield_10014` (or `"No Epic"`)
- `flagged`: `customfield_10021` is non-empty
- `blocked_by`: issuelinks where `type.inward = "is blocked by"` AND blocker status not in {Closed, Verified, Done}
- `stale`: status in {In Progress, Review} AND `updated` older than 5 business days from `{TODAY}`

---

### 3. Build Hierarchy and Rollups

Group: Feature → Epics → Issues.
Orphan groups: `(No Feature)`, `(No Epic)`, `(Unlinked Bugs)`.

**Done states** (from Laws):

- Stories/Tasks/Spikes: Closed
- OCPEDGE Bugs: Closed
- OCPBUGS Bugs: Verified, Closed
- Epics: Closed, Dev Complete

**Per-Epic rollup:**

| Field | Calculation |
|---|---|
| `total_issues` | count of all child issues |
| `done_issues` | issues in done state |
| `total_sp` | sum of SP (bugs always 0) |
| `done_sp` | SP of done issues |
| `remaining_sp` | SP of non-done issues |
| `completion_pct` | `done_sp / total_sp × 100`; fallback: `done_issues / total_issues × 100` if total_sp = 0 |
| `unpointed_count` | non-Bug issues with SP null or 0 |
| `blocked_count` | flagged OR blocked_by non-empty OR "Blocked" in labels |
| `unassigned_count` | no assignee |

**Per-Feature rollup:** aggregate epics; add `epic_count` and `done_epics`.

**Release totals:**

- `total_remaining_sp` = sum of all epics' `remaining_sp`
- `max_sp_capacity` = `remaining_sprint_count` (from sprints.json) × `total_sp_per_sprint` (from `.roster.json`)

---

### 4. Refinement Reassessment

After building the hierarchy, reassess `epics_appear_refined` for features that the transform did not already mark as refined. For each feature where `spike_missing = true` AND `spike_on_epic = false` AND `epics_appear_refined = false` AND feature status is not "New" or "Refinement":

1. Get the feature's child epics from the hierarchy
2. Skip features with 0 epics — they cannot be refined via epics
3. For each epic, read its `description` (from `epics.json`) and examine the child stories/tasks created under it (from the hierarchy)
4. An epic looks refined if its description describes work to be done AND the existing child stories appear to cover that described work — the stories don't need to be complete, but they should exist and address the scope outlined in the description
5. If **all** of the feature's epics look refined by this assessment, override `epics_appear_refined = true` for that feature

Update `features_refined_via_epics` count accordingly.

---

### 5. Risk Assessment

Read `refinement_sprint_closed` from `sprints.json`.

**7a — Schedule Risk** — Skip entirely if `refinement_sprint_closed = false`.

If `refinement_sprint_closed = true`, per Feature:

| Condition | Status |
|---|---|
| status ∈ {Done, Closed} | ✅ Complete |
| 0% complete AND ≤ 2 dev sprints remaining | 🔴 Critical |
| 0% complete AND ≤ 4 dev sprints remaining | 🟡 At Risk |
| completion_pct ≥ expected_dev_pct | 🟢 On Track |
| completion_pct ≥ expected_dev_pct × 0.75 | 🟡 Slightly Behind |
| completion_pct < expected_dev_pct × 0.75 | 🔴 At Risk |
| no Epics AND ≥ 1 dev sprint remaining | 🔴 Unplanned |

**7b — Staffing:**

- Feature `sme = "None"` → 🔴 "No SME assigned" — Action: "Assign SME this sprint"
- Feature `qa_contact = "None"` AND status ≠ Closed → 🟡 "No QA contact"
- Feature `docs_approver = "None"` → 🟢 "No docs approver"
- Epic `assignee = "Unassigned"` → 🟡 "No epic DRI"
- Epic `qa_contact = "None"` AND status ≠ Closed → 🟡 "No epic QA contact"

**7c — Refinement — Spike Rules** (based on `refinement_sprint_closed`):

Evaluate in this order — first match wins:

1. `spike_status = "Closed"` → ✅ "Closed" — direct spike completed, no risk
2. `spike_missing` AND (`spike_on_epic = true` OR `epics_appear_refined = true`) → ✅ "Via epics" — no spike risk
3. If `refinement_sprint_closed = false`:
   - `spike_missing` → 🔴 "No refinement spike — SME must create one in Sprint {REFINEMENT_SPRINT_NUM} that blocks this Feature"
   - spike exists AND NOT `spike_in_ref_sprint` → 🟡 "Spike not in refinement sprint — move to Sprint {REFINEMENT_SPRINT_NUM}"
   - spike exists AND `spike_in_ref_sprint` AND status ≠ Closed → 🟢 "Spike in progress (expected)"
4. If `refinement_sprint_closed = true`:
   - `spike_overdue = true` → 🔴 "Refinement spike not closed — refinement incomplete"
   - `spike_missing` → 🔴 "No refinement spike found; delivery epics may be under-refined"

**7c — Refinement — General:**

- Feature `has_ac = false` → 🟡 "Missing acceptance criteria"
- Feature `size = "Unsized"` → 🟡 "Feature not sized"
- Feature `epic_count = 0` → 🔴 "No epics — unplanned"
- Epic `has_ac = false` → 🟡 "Epic missing AC"
- Epic `size = "Unsized"` → 🟡 "Epic not sized"
- Epic `total_issues = 0` → 🟡 "Empty epic — no stories"
- Story/Task `sp null or 0` → 🟡 "Needs estimation"
- Story/Task `assignee = "Unassigned"` → 🟡 "Needs owner"

**7d — Blocked/Stalled:**

- `flagged = true` → 🔴 "Impediment flagged"
- `blocked_by` non-empty → 🔴 "Blocked by {keys}"
- `"Blocked"` in labels → 🔴 "Labeled Blocked"
- `"Parked"` in labels → 🟡 "Parked"
- `stale = true` → 🟡 "Stale — no update in 5+ business days"

**7e — Release-Level:**

- XL-sized epic AND `remaining_sprint_count ≤ 2` → 🔴 "XL-sized epic unlikely to complete"
- L-sized epic AND `remaining_sprint_count ≤ 1` → 🔴 "L-sized epic at risk"
- `total_remaining_sp > max_sp_capacity` → 🔴 "Capacity risk"
- (if `refinement_sprint_closed` AND `total_features > 0`) `(features_missing_spike - features_refined_via_epics) / total_features > 0.5` → 🔴 "Systematic refinement gap"
- (if `refinement_sprint_closed` AND `total_features > 0`) `(features_with_closed_spike + features_refined_via_epics) / total_features < 0.75` → 🟡 "Refinement coverage below 75%"

---

### 6. Write Output

Write to `{WORKDIR}/analysis.md` with this exact sentinel structure:

```text
===ANALYSIS_META===
{
  "total_features": <int>,
  "features_on_track": <int>,
  "features_at_risk": <int>,
  "features_complete": <int>,
  "high_risk_count": <int>,
  "medium_risk_count": <int>,
  "low_risk_count": <int>,
  "overall_health": "Critical|At Risk|On Track|Complete",
  "actual_completion_pct": <float>,
  "expected_dev_completion_pct": <float>,
  "features_with_spike": <int>,
  "features_with_closed_spike": <int>,
  "features_missing_spike": <int>,
  "features_spike_on_epic": <int>,
  "features_refined_via_epics": <int>,
  "remaining_sp": <int>,
  "max_sp_capacity": <int>,
  "capacity_risk": <bool>,
  "top_risks": ["<concise description>", ...],
  "sprint_recommendation": "<one sentence priority for this sprint>"
}
===END_META===

===SECTION:DASHBOARD===
| Key | Feature/Initiative | Type | Status | SME | QA | Size | Refn Spike | Epics Done | Progress | Risk |
|---|---|---|---|---|---|---|---|---|---|---|
(one row per feature, sorted by Jira rank — preserve the priority order returned by the JQL query)
Spike column: ✅ Closed | ✅ Via epics | 🔄 In Progress | ⚠️ Missing | ⏳ Open
===END_SECTION===

===SECTION:FEATURE_DETAIL===
(one subsection per feature, sorted by Jira rank — same order as the dashboard)

### OCPSTRAT-XXX: {Summary}

**Type**: {type} | **Status**: {status} | **Health**: {emoji}
**SME**: {sme} | **QA**: {qa_contact} | **Docs**: {docs_approver}
**Refinement Spike**: {spike_key — ✅ Closed | ✅ Via epics | 🔄 In Progress | ⚠️ Missing | ⏳ Open}
**Progress**: {done_sp}/{total_sp} SP ({pct}%) — {done_epics}/{epic_count} epics complete
**Refinement**: {✅ Has AC | ⚠️ Needs AC} | **Sized**: {✅ | ⚠️ Unsized}

#### Epics
| Epic | DRI | QA | Size | Issues | Progress | Status | Health |

#### Risks & Gaps
- {severity}: {description} — Action: {action}

#### Actions
- [ ] {action} — Owner: {owner}

===END_SECTION===

===SECTION:EPIC_DETAIL===
(only epics with blocked, stale, flagged, or unpointed issues)

### OCPEDGE-XXX: {Epic Summary}

**DRI**: {assignee} | **QA**: {qa_contact} | **Progress**: {done}/{total} SP

| Issue | Type | DRI | SP | Status | Sprint | Flags |
|---|---|---|---|---|---|---|

Flag legend: 🚫 Blocked | ⏸️ Parked | ⚠️ Unpointed | 🔴 Flagged | 💤 Stale
===END_SECTION===

===SECTION:RISK_REGISTER===
### 🔴 High Priority
| # | Issue | Risk Type | Description | Owner | Action |
|---|---|---|---|---|---|

### 🟡 Medium Priority
| # | Issue | Risk Type | Description | Owner | Action |
|---|---|---|---|---|---|

### 🟢 Low / Informational
| # | Issue | Risk Type | Description | Owner | Action |
|---|---|---|---|---|---|
===END_SECTION===

===SECTION:REFINEMENT_BACKLOG===
### Features/Initiatives
- OCPSTRAT-XXX — Missing: {items}

### Epics
- OCPEDGE-XXX — Missing: {items}

### Stories/Tasks (Unpointed or Unassigned)
- OCPEDGE-XXX (Epic: OCPEDGE-YYY) — {issue}
===END_SECTION===

===SECTION:SPRINT_FORECAST===
| Sprint | State | Projected SP | Cumulative | Cumulative % | Notes |
|---|---|---|---|---|---|
Use `total_sp_per_sprint` (from `.roster.json`) as the default velocity if no completed dev sprints exist.
Flag if projected completion at branch cut < 85% → add ⚠️ in Notes.
===END_SECTION===

===SECTION:ACTIONS===
### This Sprint — Immediate
1. {Action} — Owner: {person}

### Next Sprint
1. {Action} — Owner: {person}

### Grooming / Planning
1. {Action} — Target: Sprint {N} grooming
===END_SECTION===
```
