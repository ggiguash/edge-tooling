# bug-reproduce-tna-tnf

Automated OpenShift bug reproduction for Two-Node with Arbiter (TNA) and Two-Node with Fencing (TNF) topologies. Given a Jira bug ID, this plugin fetches the bug details, detects the target topology, deploys a cluster via dev-scripts, monitors for the bug condition, executes reproduction steps, collects logs, and generates a findings report.

**This skill must be run from the [Two-Node Toolbox (TNT)](https://github.com/openshift-eng/two-node-toolbox) repo**, specifically from `two-node-toolbox/deploy/` or `two-node-toolbox/deploy/openshift-clusters/`. Running it from any other directory will result in an error.

## Installation

Install via Claude Code's plugin system:

```text
/plugin marketplace add openshift-eng/edge-tooling
/plugin install bug-reproduce-tna-tnf
```

## Prerequisites

1. Claude Code session open at the **Two-Node Toolbox repo** (`two-node-toolbox/deploy/` or `two-node-toolbox/deploy/openshift-clusters/`)
2. EC2 instance running with `make inventory` completed
3. EC2 configured (`./configure`) and SSH-accessible
4. Pull secret at `roles/dev-scripts/install-dev/files/pull-secret.json`
5. Jira credentials set in `~/.bashrc`:
   ```bash
   export JIRA_USERNAME="your-email@redhat.com"
   export JIRA_API_TOKEN=$(cat ~/.jira-token 2>/dev/null)
   ```

## Usage

```
/bug-reproduce-tna-tnf OCPBUGS-66217
```

One argument: a Jira issue key. The skill handles everything else:

1. **Bug Analysis** -- Fetches the bug from Jira (description + comments), detects topology (arbiter or fencing), classifies bug category, extracts reproduction steps, detects install method (IPI/agent/kcli), and determines the OCP version. Stops if the bug is a test issue (not a product bug) or if the dev-scripts environment cannot reproduce the conditions.
2. **Cluster Deployment** -- Updates the dev-scripts config, uploads day-0 manifests if needed, and runs the Ansible deployment playbook. Monitors deployment every 10 minutes for early failure detection. Cleans and retries on failure (with user approval).
3. **Cluster Ready** -- Waits for all nodes Ready, MCPs updated, and COs healthy. Detects during-install bugs. Applies day-1 manifests if needed.
4. **Bug Reproduction** -- Executes the reproduction steps extracted from the Jira bug on the healthy cluster. This is the core phase for most bugs (post-install steps like pcs commands, node reboots, backup/restore, oc apply, etc.).
5. **Log Collection** -- Collects category-targeted logs (etcd, fencing, MCO, NTO, networking, etc.), rsyncs locally, and generates a findings report.

The cluster is **always left running** after the skill completes so the user can SSH in and inspect.

## Supported Topologies

- **arbiter** -- Two-Node with Arbiter (TNA): 2 masters + 1 arbiter node
- **fencing** -- Two-Node with Fencing (TNF): 2 masters with BMC-based fencing

Other topologies (3node, SNO, MicroShift) are not supported by this plugin.

## Output

- Logs saved to `/tmp/bug-reproduce-tna-tnf-<BUG_ID>/`
- Findings report written to `docs/<bug-id>-findings.md` in the TNT repo
- Cluster left running for manual inspection

## Requirements

- **Claude Code:** >= 1.0.0
- **Category:** debug
- **MCP:** mcp-atlassian (Jira access)
- **Working directory:** Two-Node Toolbox repo (deploy directory)

## Author

nhamza
