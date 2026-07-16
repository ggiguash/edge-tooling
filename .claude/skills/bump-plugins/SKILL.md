---
name: bump-plugins
description: Use when preparing a branch or PR that changes marketplace plugins — analyzes commits vs a base ref, suggests a major/minor/patch version bump per changed plugin with reasoning, and applies the bumps on confirmation
user-invocable: true
argument-hint: "[base-ref] (default: merge-base with upstream main)"
allowed-tools: Bash, Read, Edit, Glob, Grep, AskUserQuestion
---

# bump-plugins

Suggest and apply semver bumps for marketplace plugins changed on the current branch.

## Synopsis

```text
/bump-plugins [base-ref]
```

`base-ref` overrides the comparison base (a branch, tag, or SHA). Without it, the base
is the merge-base of `HEAD` with the upstream `main` — the `main` branch of whichever
remote points at `github.com/openshift-eng/edge-tooling`, discovered by URL rather
than assuming a remote name.

## Prerequisites

- Run from the repository root (the `./marketplace` CLI must be present)
- The branch under analysis is checked out as `HEAD`

## Steps

### 1. Determine the base ref

- If `$ARGUMENTS` is non-empty, use it as the base ref; verify it resolves with
  `git rev-parse --verify <base-ref>` and stop with a clear error if it does not.
- Otherwise find the upstream remote: the entry in `git remote -v` whose fetch URL
  matches `github.com[:/]openshift-eng/edge-tooling` (any protocol, optional `.git`
  suffix). Do not assume its name — it may be `origin`, `upstream`, `openshift`, etc.
  - Run `git fetch <upstream-remote> main` first so the local tracking ref is current,
    then use `git merge-base <upstream-remote>/main HEAD`. If the fetch fails (e.g.
    offline), check whether `<upstream-remote>/main` already exists locally; if it does,
    use it and note the stale ref in the report. If it does not exist, fall through to
    the fallback chain below.
  - If no remote matches, or the upstream tracking ref is unavailable after a failed
    fetch, fall back to `git merge-base origin/main HEAD`, then
    `git merge-base main HEAD`. If none of these refs exist, stop with a clear error.
    Note the fallback in the report: a fork's `main` can be far behind upstream, which
    would misattribute old upstream commits to the branch.
- If the base resolves to the same commit as `HEAD`, stop: there are no branch commits
  to analyze.

### 2. Detect changed plugins

- Run `git diff --name-only <base>..HEAD -- plugins/` and group the paths by top-level
  directory under `plugins/`.
- Classify each directory:
  - **Active plugin**: `plugins/<name>/.claude-plugin/plugin.json` exists at `HEAD`.
    Include in Step 3 for version analysis.
  - **New plugin** (added on the branch): `plugin.json` exists at `HEAD` but not at
    `<base>` (`git show <base>:plugins/<name>/.claude-plugin/plugin.json` fails).
    Include in Step 3 — there is no base version to compare, so skip the
    "already bumped" check and report the current version as-is with a note that
    this is a new plugin.
  - **Deleted plugin**: paths appear in the diff but `plugin.json` does not exist at
    `HEAD`. Report it in the Step 4 table as removed (no bump possible). Do not
    include in Step 3.
  - **Non-plugin directory**: no `plugin.json` at `HEAD` and no diff paths that
    previously had one at `<base>`. Ignore silently.
- If no active, new, or deleted plugin directories changed, report that and stop.

### 3. Classify each changed plugin

For each changed plugin, read `git log --oneline <base>..HEAD -- plugins/<name>` and
`git diff <base>..HEAD -- plugins/<name>`, then pick the **highest** applicable level:

- **major** — breaking for plugin users:
  - a skill, agent, or slash command is removed or renamed
  - slash-command arguments change incompatibly (removed, reordered, made required)
  - new required prerequisites (credentials, tools, cluster state)
  - a hook or MCP server is removed
  - an output format that consumers depend on changes incompatibly
- **minor** — backward-compatible additions:
  - new skill, agent, hook, or MCP server
  - new optional arguments or flags
  - new capabilities added to an existing skill
- **patch** — everything else:
  - bug fixes, prompt clarifications and tweaks, docs, typos, lint fixes
  - internal refactors with unchanged user-facing behavior

Then check whether the branch already bumped the version: for plugins that existed at
the base (not new plugins), compare the `version` field from
`git show <base>:plugins/<name>/.claude-plugin/plugin.json` against the one at `HEAD`.
If it was already bumped, do not re-suggest — verify the existing bump is at least the
suggested level and report the plugin as "already bumped" (or "already bumped, but
under-scoped" when e.g. the branch bumped patch while the diff warrants minor or
major). For new plugins (no base version), skip this check.

### 4. Present suggestions and confirm

Present one table for all changed plugins:

| Plugin | Base version | Current version | Suggested bump | New version | Reasoning |
|--------|--------------|-----------------|----------------|-------------|-----------|

Column semantics: **Base version** is the version at `<base>` (or "—" for new plugins).
**Current version** is the version at `HEAD`. **Suggested bump** is the bump level to
apply (or "none" / "already bumped" / "removed"). **New version** is the target version
after applying the bump (or "—" when no action needed).

Reasoning is one line citing the driving commit(s) or change. Include "already bumped"
rows for completeness, marked as requiring no action. Include deleted-plugin rows
marked as "removed".

Then confirm with AskUserQuestion before changing anything: apply all suggestions,
apply a subset (multi-select of plugins), or skip. Never edit files without this
confirmation.

### 5. Apply confirmed bumps

1. Edit the `version` field in each confirmed
   `plugins/<name>/.claude-plugin/plugin.json`.
2. Run `./marketplace catalog-update` once to sync the central
   `.claude-plugin/marketplace.json` from the per-plugin manifests.
3. Run `./marketplace validate <name>` for each bumped plugin and report failures.
4. Show `git diff --stat` of the result. Leave the changes uncommitted unless the user
   asks; the repo convention is a dedicated "Bump plugins" commit.

## Examples

**User:** `/bump-plugins`

**Claude:** Finds the remote tracking `openshift-eng/edge-tooling`, fetches its `main`,
computes the merge-base with `HEAD`, detects that `lvms-ci` and
`microshift-ci` changed, suggests a patch bump for each with one-line reasoning, asks
for confirmation, then edits both `plugin.json` files and runs
`./marketplace catalog-update` and `./marketplace validate`.

**User:** `/bump-plugins 07a4fd9`

**Claude:** Same analysis, but comparing `HEAD` against commit `07a4fd9`.

## Edge Cases

- **No remote tracks `openshift-eng/edge-tooling`**: fall back per Step 1 and state
  clearly which base was used — suggestions against a stale fork `main` may be wrong.
- **Dirty working tree**: if `git status --porcelain` shows uncommitted changes to any
  `plugin.json` or to `.claude-plugin/marketplace.json`, warn before Step 5 and let the
  user decide whether to proceed.
- **Version already bumped on the branch**: handled in Step 3 — report instead of
  re-suggesting; flag under-scoped bumps.
- **Prerelease/build-metadata versions** (e.g. `1.2.0-rc.1`): the marketplace semver
  regex allows suffixes. Bump the numeric core and ask before dropping the suffix.
- **New plugin added on the branch**: `plugin.json` exists at `HEAD` but not at
  `<base>`. Handled in Step 2 — include it in analysis, skip the base-version
  comparison in Step 3, show "—" for base version in the table.
- **Plugin deleted on the branch**: handled in Step 2 — report it in the table as
  removed, no bump possible.
- **Version at HEAD lower than at base** (accidental downgrade): flag it explicitly
  instead of suggesting a bump on top.

## Notes

- The per-plugin `plugin.json` is the source of truth; `.claude-plugin/marketplace.json`
  is a synced catalog. Never hand-edit the catalog — `./marketplace catalog-update`
  regenerates it.
- Steps 1–4 are read-only; only Step 5 modifies files, and only after explicit
  confirmation in Step 4.
