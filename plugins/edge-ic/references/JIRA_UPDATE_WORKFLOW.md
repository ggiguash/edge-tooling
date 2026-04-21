# Jira Update Workflow

Workflow for updating Jira issues from TODO accomplishments.

## Process

1. Read today's TODO file
2. Extract Jira ticket references from completed and in-progress items
3. For each ticket:
   - Show accomplishment
   - Prompt: Add comment? [Y/n]
   - Prompt: Update status? [Y/n]
   - Prompt: Add worklog? [Y/n]
4. Execute updates via MCP tools
5. Display summary with links

## Best Practices

- Run at end of day or before standup
- Always review before confirming
- Include context in comments
- Update status only when appropriate
