---
description: Resume an existing project workspace
argument-hint: [name-or-number]
---

# Resume Project Workspace

Resume work on an existing project. Projects live under `projects/`.

## Step 1: Resolve Project

Run `scripts/resume-project.py $ARGUMENTS` via Bash. Parse the JSON output
and handle by `status`:

- **`ok`** — proceed to Step 2.
- **`no_argument`** — present the first 3 `alternatives` as AskUserQuestion
  options plus "See all projects" (which shows the full list). Re-run the
  script with the chosen name.
- **`not_found`** or **`out_of_range`** — show `error_message`, present
  `alternatives` as a picker, re-run with the chosen name.
- **`no_projects`** — show `error_message` and stop.

Store the `project` object from the JSON as `P` for the remaining steps.

## Step 2: Load Project Index

1. Read `P.context_file` using the Read tool (skip if null).
2. **Do NOT read `P.repo_context_files` yet.** Store the list for on-demand
   loading (see Step 5).

## Step 3: Present Summary

Display a structured summary:

```text
## Project: <P.name>

| Field | Value |
|-------|-------|
| **Type** | <P.frontmatter.type or "Unknown"> |
| **Created** | <P.frontmatter.created or "Unknown"> |
| **Status** | <P.frontmatter.status or "Unknown"> |
| **JIRA** | <P.frontmatter.jira or "None"> |
| **Repos** | <comma-separated P.frontmatter.repos, or "None specified"> |
```

**If `P.has_reference_files`:**
Show the reference files table from `P.reference_files`. If
`P.unregistered_files` is non-empty, note them. Show checklist progress
as `P.checklist.checked`/`P.checklist.total`. Add: "Detail files will
be loaded based on what you choose to work on."

**If not:** Show `P.all_files` list. Add: "Full project context loaded."

**If `P.repo_context_files` is non-empty:**
Show an "Available Repo Context" table:

```text
| Repo | Source | Path |
|------|--------|------|
| <repo> | <source> | `<path>` |
```

Add: "Repo context files will be loaded on demand when you work on a
specific repo."

## Step 4: Task Selection

**4a.** Build a task menu from `P.checklist.unchecked_items`. For each
item, match its text and `section` against `P.reference_files` descriptions
to determine which detail files are relevant.

**4b.** Present via AskUserQuestion with options like:

- "Next: \<task text\> (loads: file1.md, file2.md)"
- "Review all project notes (loads: all detail files)"
- "Something else"

Skip file annotations if `P.has_reference_files` is false (monolithic
project — all content is already in context from Step 2).

**4c.** After the user picks, read the mapped detail files using Read.
Confirm what was loaded.

**4d.** Suggest relevant skills from `P.skill_suggestions`.

**4e.** Remind: "If you create new detail files during this session, add
them to the Reference Files table in CLAUDE.md."

## Step 5: Lazy Repo Context Loading

**Do NOT load repo context files until needed.** You have the manifest from
`P.repo_context_files` — use it reactively:

- When the user's query involves a specific repo, **read its context file
  then** (from `P.repo_context_files` matching that repo name).
- When a task from Step 4 maps to specific repos, load their context at
  that point.
- If the user asks to "load all context", comply — but default to lazy.

This keeps the context window lean for multi-repo projects where you
typically work in one repo at a time.

---

## Notes

- Always use the Read tool for files, never cat via Bash
- Use Bash for `ls`, `find`, and `mkdir -p` operations
- If no context file exists, ask the user for context — don't fabricate one
