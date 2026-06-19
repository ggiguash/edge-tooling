# Morning Briefing Output Format

Reference template for the `edge-ic:morning` skill output.

## Template

```
☀ Morning Briefing — {month} {day}, {year}

  {sprint_name} — {days_remaining} of {total_days} days remaining
  Story Points: {points_completed} / {points_total} completed ({percentage}%)
  {progress_bar}

  {summary_line}

── QA Ready ──────────────────────────────────────────────
  {KEY}  {summary}          ({requester_note})
  {KEY}  {summary}          {link}

── Sprint Backlog (not Done) ─────────────────────────────
  {Status}:
    {KEY}  {summary}          {link}

── Carry-over from Yesterday ─────────────────────────────
  - {item_text}

── Your Open PRs ─────────────────────────────────────────
  {repo}#{pr_number}  "{title}"     open {days_open} · idle {days_idle} · missing: {labels}

── RHEL Verification Queue ───────────────────────────────
  {count} RHEL tickets awaiting verification
  {KEY}  {summary}
  → Run /two-node:create-rhel-stories to create tracking stories

── Reminders ─────────────────────────────────────────────
  ⚠ {sprint_name} ends in {days} days — prepare tasks for next sprint
  ⚠ Quarter ends in {days_left} days ({quarter_end_date})
    → Complete Quarterly Connection in Workday
    → Submit RewardZone points: https://rewardzone.redhat.com/
```

## Rules

- **Empty sections**: omit entirely (no header, no blank lines)
- **All sections empty**: print "Nothing on your plate — enjoy the quiet morning"
- **Summary line**: count items per non-empty section, join with ` · ` (e.g., "5 QA tasks ready · 3 sprint items")
- **Links**: plain URLs, not markdown — terminal-friendly
- **Progress bar**: 20 characters wide, filled proportionally: `████████████░░░░░░░░`
  - Filled char: `█` (U+2588)
  - Empty char: `░` (U+2591)
- **Requester note**: if a QA request was found in comments, show `(requested by @{author} in comment)`, otherwise show the JIRA link
- **Sprint urgency**: last 3 days → reminder in Reminders section; last day → use 🔴 prefix instead of ⚠

## Summary Line Labels

| Section | Label format |
|---------|-------------|
| QA Ready | `{n} QA task(s) ready` |
| Sprint Backlog | `{n} sprint item(s)` |
| Carry-over | `{n} carry-over(s)` |
| Open PRs | `{n} PR(s)` |
| RHEL Queue | `{n} RHEL ticket(s)` |
| Quarterly | `⚠ quarterly reminder` (no count) |
| Sprint Urgency | `⚠ sprint ending soon` (no count) |
