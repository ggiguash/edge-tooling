# Morning Briefing Output Format

Reference template for the `edge-ic:morning` skill output.

All panels use rounded box-drawing characters (`╭╮╰╯│─`). The header panel contains the sprint info and summary line. Each data section gets its own panel. Empty sections are omitted entirely — no empty box.

## Title Banner

The output begins with the configured title rendered in block pixel characters (▀ ▄ █), centered above the panels. Default title: `Morning Edge`

```text
              █▄ ▄█ █▀▀█ █▀▀▄ █▄ █ █ █▄ █ █▀▀▀
              █ ▀ █ █  █ █▄▄▀ █ ▀█ █ █ ▀█ █ ▀█
              ▀   ▀ ▀▀▀▀ ▀  ▀ ▀  ▀ ▀ ▀  ▀ ▀▀▀▀
              █▀▀▀ █▀▀▄ █▀▀▀ █▀▀▀
              █▀▀  █  █ █ ▀█ █▀▀
              ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀
```

### Title Construction Rules

- **Font**: block pixel using `▀ ▄ █` — each letter is 3 rows tall, 3-5 columns wide
- **Layout**: two-word titles stack vertically, left-aligned at the same indent; single-word titles use one block
- **Centering**: indent so the longer word is centered relative to the 60-char panel width
- **Long titles (> 45 chars rendered)**: fall back to spaced capital letters (`M O R N I N G   E D G E`)
- **Blank line** after the title, before the header panel

### Block Pixel Character Map

Each letter is 3 rows tall. Most are 4 columns wide; M and W are 5; I is 1; T is 3. Letters separated by 1 space.

```text
A:█▀▀█  B:█▀▀▄  C:█▀▀▀  D:█▀▀▄  E:█▀▀▀  F:█▀▀▀  G:█▀▀▀
  █▀▀█    █▀▀▄    █       █  █    █▀▀     █▀▀     █ ▀█
  ▀  ▀    ▀▀▀▀    ▀▀▀▀    ▀▀▀▀    ▀▀▀▀    ▀       ▀▀▀▀

H:█  █  I:█  J: ▀█  K:█ ▄▀  L:█     M:█▄ ▄█  N:█▄ █
  █▀▀█    █    █    █▀▄     █       █ ▀ █    █ ▀█
  ▀  ▀    ▀   ▀▄▄▀   ▀  ▀    ▀▀▀    ▀   ▀    ▀  ▀

O:█▀▀█  P:█▀▀▄  Q:█▀▀█  R:█▀▀▄  S:█▀▀▀  T:▀█▀  U:█  █
  █  █    █▀▀     █  █    █▄▄▀    ▀▀▀█     █     █  █
  ▀▀▀▀    ▀       ▀▀▀▄    ▀  ▀    ▀▀▀▀     ▀     ▀▀▀▀

V:█  █  W:█   █  X:▀▄ ▄▀  Y:█  █  Z:▀▀▀█
  ▀▄▄▀    █ █ █    ▀█▀     ▀▄▄▀    ▄▀▀
   ▀▀     ▀▀ ▀▀   ▄▀ ▀▄     ▀▀     ▀▀▀▀
```

## Template

```text
              █▄ ▄█ █▀▀█ █▀▀▄ █▄ █ █ █▄ █ █▀▀▀
              █ ▀ █ █  █ █▄▄▀ █ ▀█ █ █ ▀█ █ ▀█
              ▀   ▀ ▀▀▀▀ ▀  ▀ ▀  ▀ ▀ ▀  ▀ ▀▀▀▀
              █▀▀▀ █▀▀▄ █▀▀▀ █▀▀▀
              █▀▀  █  █ █ ▀█ █▀▀
              ▀▀▀▀ ▀▀▀▀ ▀▀▀▀ ▀▀▀▀

╭──────────────────────────────────────────────────────────╮
│  ☀  Morning Briefing — {month} {day}, {year}             │
│                                                          │
│  **{sprint_name}** — {days_remaining} of {total_days} days remaining
│  **Story Points:** {completed} / {total} ({pct}%)        │
│  {progress_bar}                                          │
│                                                          │
│  > {summary_line}                                        │
╰──────────────────────────────────────────────────────────╯

╭─ » QA Ready ─────────────────────────────────────────────╮
│  **{KEY}**  {summary}          ({requester_note})         │
│  **{KEY}**  {summary}          {link}                     │
╰──────────────────────────────────────────────────────────╯

╭─ » Sprint Backlog ───────────────────────────────────────╮
│  {Status}:                                                │
│    **{KEY}**  {summary}  [{sp} SP]  {link}                │
╰──────────────────────────────────────────────────────────╯

╭─ » Carry-over from Yesterday ────────────────────────────╮
│  - {item_text}                                            │
╰──────────────────────────────────────────────────────────╯

╭─ » Your Open PRs ────────────────────────────────────────╮
│  **{repo}#{number}**  "{title}"                           │
│    open {days} · idle {days} · {n} unresolved · missing: {labels}
╰──────────────────────────────────────────────────────────╯

╭─ » PRs Awaiting Your Review ─────────────────────────────╮
│  **{repo}#{number}**  "{title}"       open {days}         │
│    {link}                                                 │
╰──────────────────────────────────────────────────────────╯

╭─ » RHEL Verification Queue ──────────────────────────────╮
│  {count} RHEL tickets awaiting verification               │
│  **{KEY}**  {summary}                                     │
│  → Run /two-node:create-rhel-stories to create stories    │
╰──────────────────────────────────────────────────────────╯

╭─ » Reminders ────────────────────────────────────────────╮
│  ⚠ **{sprint_name}** ends in {days} days — prepare next  │
│  ⚠ Quarter ends in {days_left} days ({quarter_end_date})  │
│    → Complete Quarterly Connection in Workday             │
│    → Submit RewardZone points: https://rewardzone.redhat.com/
╰──────────────────────────────────────────────────────────╯
```

## Panel Construction

All borders target **60 visual columns** wide (outer `╭`/`╰` to outer `╮`/`╯`).

- **All borders**: **60 raw chars** (`╭` + 58×`─` + `╮`). Section markers use `»` (narrow, 1 visual column) so all borders are uniformly 60 raw = 60 visual
- **Content lines**: left `│` + 2-space indent; right `│` aligned at column 60 where content fits; long summaries wrap to a continuation line; bare URLs may extend past the border for usability
- **Corners**: `╭` top-left, `╮` top-right, `╰` bottom-left, `╯` bottom-right
- **Section title**: embedded in top border: `╭─ » {title} ─...─╮`

## Section Markers

All sections use `»` as a prefix in the top border. The `⚠` symbol is reserved for warning content inside panels (reminders, error notes) — not used as a section marker.

## Progress Bar

10 colored squares wide with bracket borders `▐...▌`, gradient fill from red to green:

- Positions 1-3: 🟥 (red)
- Positions 4-5: 🟠 (orange)
- Positions 6-7: 🟡 (yellow)
- Positions 8-10: 🟢 (green)
- Unfilled positions use `░` (U+2591)
- Append `{percentage}%` after the closing bracket

Examples:

- 0%:   `▐░░░░░░░░░░▌ 0%`
- 20%:  `▐🟥🟥░░░░░░░░▌ 20%`
- 50%:  `▐🟥🟥🟥🟠🟠░░░░░▌ 50%`
- 80%:  `▐🟥🟥🟥🟠🟠🟡🟡🟢░░▌ 80%`
- 100%: `▐🟥🟥🟥🟠🟠🟡🟡🟢🟢🟢▌ 100%`

## Rules

- **Empty sections**: omit the entire panel (no empty box)
- **All sections empty**: show only the header panel with "Nothing on your plate — enjoy the quiet morning"
- **Summary line**: count items per non-empty section, join with ` · `. Prefix with `>`
- **Ticket keys**: always **bold** (`**KEY**`)
- **Sprint name**: always **bold** in header and reminders
- **Links**: plain URLs, not markdown — terminal-friendly
- **Requester note**: if a QA request was found in comments, show `(requested by @{author} in comment)`, otherwise show the JIRA link
- **Sprint urgency**: last 3 days → reminder in Reminders panel; last day → use 🔴 prefix instead of ⚠

## Summary Line Labels

| Section | Label format |
|---------|-------------|
| QA Ready | `{n} QA task(s) ready` |
| Sprint Backlog | `{n} sprint item(s)` |
| Carry-over | `{n} carry-over(s)` |
| Open PRs | `{n} open PR(s)` |
| Review Queue | `{n} PR(s) to review` |
| RHEL Queue | `{n} RHEL ticket(s)` |
| Quarterly | `⚠ quarterly reminder` (no count) |
| Sprint Urgency | `⚠ sprint ending soon` (no count) |

## Error Notes

Errors go in their own panel at the bottom (uses `⚠` instead of `»`):

```text
╭─ ⚠ Notes ────────────────────────────────────────────────╮
│  ⚠ Could not reach JIRA — QA tasks, sprint, RHEL skipped │
│  ⚠ Could not fetch PR dashboard — open PRs skipped       │
╰──────────────────────────────────────────────────────────╯
```
