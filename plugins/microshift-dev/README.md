# MicroShift Dev Tools

A collection of development tools for MicroShift workflows.

## Skills

### golang-cve-analyzer

Analyzes MicroShift Jira CVE tickets against the Go toolchain CVEs fixed in the latest Brew nightly builds.

Given a Jira ticket ID, the skill:

1. Validates the ticket is a CVE bug with MicroShift component (via Jira MCP)
2. Extracts the target OCP minor version from the ticket
3. Finds the latest MicroShift nightly Brew build for that version
4. Discovers which Go toolchain was used to build it
5. Checks if the ticket's CVE is already fixed in that Go version's changelog

```bash
/microshift-dev:golang-cve-analyzer OCPBUGS-12345
/microshift-dev:golang-cve-analyzer OCPBUGS-12345 --verbose
```

## Prerequisites

| Requirement | Source |
|-------------|--------|
| VPN | Brew/Koji API access requires Red Hat VPN |
| `mcp-atlassian` plugin | Install via `/plugin marketplace add openshift-eng/edge-tooling` |
| `JIRA_USERNAME` | Your Atlassian email |
| `JIRA_API_TOKEN` | [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) |
| Python `requests` | `pip install requests` |

## Dependencies

This plugin depends on:

- **mcp-atlassian** — for Jira ticket queries
