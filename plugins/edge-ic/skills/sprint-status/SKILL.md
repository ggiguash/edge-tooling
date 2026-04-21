---
name: edge-ic:sprint-status
description: Query sprint tickets grouped by status to show progress
allowed-tools:
  - mcp__atlassian__jira_search
user-invocable: true
---

# IC: Sprint Review

Query all tickets in a given sprint and display them grouped by status to show sprint progress and identify work that needs to move.

## Task

Given a sprint number (or default to current sprint), query Jira for all active tickets and present them in a structured format grouped by status progression.

## Instructions

1. **Parse arguments**: Sprint number, `--assignee=<user>`, `--all`, `--format=<type>`
2. **Map sprint number to sprint ID**
3. **Build JQL query**:
   - **Default**: `Sprint = <sprint-id> AND statusCategory != Done`
   - **With `--all`**: `Sprint = <sprint-id>` (omit statusCategory filter)
   - **With `--assignee=<user>`**: Append `AND assignee = "<user>"` to query
   - **With both flags**: `Sprint = <sprint-id> AND assignee = "<user>"` (no statusCategory filter)
   - **Example queries**:
     - Default: `Sprint = 287 AND statusCategory != Done`
     - --all: `Sprint = 287`
     - --assignee=currentUser(): `Sprint = 287 AND statusCategory != Done AND assignee = currentUser()`
     - --all --assignee=john@example.com: `Sprint = 287 AND assignee = "john@example.com"`
4. **Query sprint tickets** using `mcp__atlassian__jira_search`
5. **Group tickets by status**: Code Review, POST, In Progress, ASSIGNED, To Do, New
6. **Format output** based on --format (table, simple, keys-only)
7. **Handle edge cases**

## Important

- Default filters out completed work
- Display statuses in workflow order (closer to done first)
- Assignee display name for readability
- Include clickable Jira links: [KEY](https://redhat.atlassian.net/browse/KEY)
