# Daily Standup Validation

The `edge-ic` plugin provides tools for validating daily standup format before posting to Slack.

## Daily Standup Format Rules

When generating daily standup for Slack:

1. **Include a header line** (e.g., "Daily Report:") at the top for proper `/copy` command alignment
2. **Use correct emoji format**:
   - `:done-circle-check:` for completed items
   - `:in-progress:` for in-progress items
   - `:jira-blocker:` for blocked items
3. **Consolidate similar bullets** - Group related items together to keep reports concise
4. **Use concise descriptions** - Be brief and direct
5. **Include Jira tickets** with format: `OCPEDGE-123: Description (https://redhat.atlassian.net/browse/OCPEDGE-123)`
6. **Render as plain text** - No code blocks, ready for direct copying

## Validation Script

Before posting daily reports to Slack, validate format:

```bash
plugins/edge-ic/bin/validate-daily-report.sh my-report.txt
```

See [validation documentation](../../plugins/edge-ic/references/validation-README.md) for complete details.
