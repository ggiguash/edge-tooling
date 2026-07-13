---
name: release-planning-analysis
description: Write actionable recommendations for a release planning risk assessment — reads pre-computed check results and produces narrative per person and per feature
allowed-tools: Read, Write
user-invocable: false
---

# release-planning: Analysis

## Purpose

Read the pre-computed planning risk checks from `checks.json` and write actionable, natural-language recommendations. All arithmetic (capacity, timeline, composite scoring) has already been computed by `run-checks.py` — this agent only interprets the results and writes narrative.

## When to Spawn

The parent release-planning skill spawns this agent during Phase 5b, after `run-checks.py` has produced `{WORKDIR}/checks.json`.

## Parameters

Substituted by the parent before spawning:

| Placeholder | Description |
|---|---|
| `{WORKDIR}` | Work directory path |
| `{VERSION}` | OCP release version (e.g., `5.0`) |

## Instructions

### Step 1: Read Data

Read `{WORKDIR}/checks.json`. This file contains all computed check results:

- `meta` — summary counts (total features, risk levels, overall risk)
- `data_quality` — per-feature gate status (PASS/WARN/FAIL)
- `capacity` — per-person assigned SP vs remaining capacity
- `timeline` — per-feature remaining work vs time left
- `assignment` — SPOFs and unassigned work
- `bug_load` — unassigned Blocker/Critical bugs
- `sizing` — T-shirt size mismatches
- `composite` — per-feature composite risk level
- `unknown_contributors` — people with work assigned who aren't in the team roster

### Step 2: Write Recommendations

Write `{WORKDIR}/recommendations.json` with this structure:

```json
{
  "executive_summary": "<3-5 sentences covering: overall risk verdict, top 2-3 risks, most critical action>",
  "per_person": [
    "<actionable recommendation per overloaded or SPOF person, referencing their SP numbers and features>"
  ],
  "per_feature": [
    "<actionable recommendation per at-risk feature, starting with HIGH composite risk>"
  ],
  "team_level": [
    "<overall team actions — capacity rebalancing, scope cuts, process changes>"
  ]
}
```

### Writing Guidelines

- **Be specific**: Reference actual numbers from `checks.json`. "Alice has 25 SP assigned but only 16 SP capacity" not "Alice is overloaded."
- **Be actionable**: Every recommendation should name a person, a feature, and a concrete action. "Move 9 SP from Alice to Bob" not "Rebalance load."
- **Prioritize HIGH composite risk features**: Address them first in per-feature recommendations.
- **Flag unknown contributors**: If `unknown_contributors` is non-empty, note that these people have work assigned but aren't in the team roster — their velocity assumptions may be wrong.
- **Data quality failures**: For features with FAIL status, recommend specific next steps (create stories, point existing stories) rather than just noting the failure.
- **Don't repeat numbers the report already shows**: The tables will have the data. Recommendations should interpret and advise, not restate.
- **Use bare Jira keys only**: Write `OCPSTRAT-2607` not `[OCPSTRAT-2607](url)`. The report assembly script adds Jira links automatically — pre-linking causes broken nested links.

## Important Notes

- This agent does NOT compute any numbers — all arithmetic is in `checks.json`
- This agent does NOT build hierarchies or read Jira data files
- This agent does NOT write markdown sections or sentinel blocks
- Output is a single JSON file with four keys
- Use natural language — be conversational and actionable
