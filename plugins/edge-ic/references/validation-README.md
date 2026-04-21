# Daily Report Validation

Tools for validating daily report format before posting to Slack.

## Files

- `plugins/edge-ic/bin/validate-daily-report.sh` - Validation script
- `plugins/edge-ic/bin/test-validate-daily-report.sh` - Test suite
- `test-fixtures/` - Test fixtures

## Quick Start

### Validate a Report

```bash
plugins/edge-ic/bin/validate-daily-report.sh my-report.txt
```

### Run Tests

```bash
plugins/edge-ic/bin/test-validate-daily-report.sh
```

## Validation Rules

The validator checks for the following formatting requirements (from `CLAUDE.md` and edge-tooling/CLAUDE.md):

### Required (failures)

1. **Header line** - Report must start with a header like "Daily Report:", "Status Update:", etc.
2. **Emoji format** - Must use Slack emoji codes:
   - `:done-circle-check:` for completed items
   - `:in-progress:` for in-progress items
   - `:jira-blocker:` for blocked items
3. **No markdown checkboxes** - Don't use `- [x]` or `- [ ]` (use emojis instead)
4. **No code blocks** - Report must be plain text (no ` ``` ` fences)

### Warnings (pass in normal mode, fail in strict mode)

1. **Jira ticket format** - Include URL: `TICKET-123: Description (https://redhat.atlassian.net/browse/TICKET-123)`
2. **Consolidation** - Reports with >20 bullets need consolidation (group related PRs/tickets)

## Usage

### Basic Validation

```bash
plugins/edge-ic/bin/validate-daily-report.sh report.txt
```

Exit codes:

- `0` - All checks passed
- `1` - Validation errors
- `2` - Warnings only (non-strict)

### Strict Mode

Enable strict mode to treat warnings as errors:

```bash
STRICT=1 plugins/edge-ic/bin/validate-daily-report.sh report.txt
```

In strict mode, missing Jira URLs and too many bullets will cause validation to fail.

### Help

```bash
plugins/edge-ic/bin/validate-daily-report.sh --help
```

## Example

```text
Daily Report:

Done: OCPEDGE-2510: Fixed deployment issue (https://redhat.atlassian.net/browse/OCPEDGE-2510)
In progress: OCPEDGE-2457: Waiting for doc writer input (https://redhat.atlassian.net/browse/OCPEDGE-2457)
```

## Testing

The test suite validates the validator against known good and bad inputs.

### Run All Tests

```bash
plugins/edge-ic/bin/test-validate-daily-report.sh
```

### Test Fixtures

Located in `test-fixtures/`:

- `valid-report.txt` - Properly formatted report
- `invalid-no-header.txt` - Missing header line
- `invalid-markdown-checkboxes.txt` - Uses Markdown instead of emojis
- `invalid-code-blocks.txt` - Contains code blocks
- `warning-missing-jira-url.txt` - Jira tickets without URLs
- `warning-too-many-bullets.txt` - Report with >20 bullets

### Adding New Tests

1. Create a new fixture file in `test-fixtures/`
2. Add a test case to `plugins/edge-ic/bin/test-validate-daily-report.sh` using `run_test` function:

```bash
run_test \
    "test-name" \
    "fixture-file.txt" \
    EXPECTED_EXIT_CODE \
    "Test description"
```

## See Also

- `CLAUDE.md` - Daily report formatting guidelines
