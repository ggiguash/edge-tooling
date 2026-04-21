# CLAUDE.md

## Repository Overview

Edge Tooling is a multi-tool deployment and development toolkit for OpenShift and edge computing environments. The repository provides automation for deploying OpenShift clusters in various configurations, managing cloud infrastructure, and setting up development workspaces.

## Tool Quick Reference

| Component | Path | Purpose |
|-----------|------|---------|
| Two-Node Toolbox | `two-node-toolbox/` | OpenShift two-node cluster deployment (arbiter/fencing topologies) |
| EC2 Deploy | `ec2-deploy/` | Standalone EC2 instance setup for development |
| SNO Deploy | `sno-deploy/` | Single Node OpenShift with DU configuration |
| Payload Monitor | `payload-monitor/` | Nightly payload health monitoring for edge topologies (SNO/TNA/TNF) |
| LVM Operator Environment | `environments/lvm-operator/` | Development workspace template for LVMS |
| Plugin Marketplace | `plugins/` | Claude Code plugin marketplace for OpenShift/edge workflows |

**Use case routing:**

- Two-node HA cluster → Two-Node Toolbox
- EC2 dev host → EC2 Deploy (often used as hypervisor for Two-Node Toolbox)
- Single-node OpenShift → SNO Deploy
- LVM Operator development → LVM Operator Environment
- Monitor nightly payload health for edge topologies → Use Payload Monitor
- Claude Code plugins for OpenShift/edge → Plugin Marketplace (`/plugin marketplace add openshift-eng/edge-tooling`)

For commands, flags, prerequisites, and workflows: read the component's README.md or Makefile.

## Common Workflows

### EC2 → Two-Node Toolbox Deployment

1. Deploy EC2 instance: `cd ec2-deploy && make deploy init`
2. Configure instance: `./configure.sh`
3. Clone two-node-toolbox on instance or use Ansible from local machine
4. Deploy cluster: `cd two-node-toolbox/deploy && make deploy arbiter-ipi`

### SNO for Single-Node Testing

1. Ensure prerequisites in `~/.sno-deploy/`
2. Deploy: `make CLUSTER="test-cluster"`
3. Access: Use credentials from `~/.sno-deploy/test-cluster/creds/`

### LVM Operator Development

1. Clone workspace: `git clone <this-repo> lvm-workspace`
2. Clone repos: `cd lvm-workspace/environments/lvm-operator/repos && git clone <lvm-operator>`
3. Develop with full context from workspace root

---

## Prerequisites Summary

| Requirement | Components | Source |
|-------------|------------|--------|
| AWS CLI + AWS_PROFILE | EC2 Deploy, Two-Node Toolbox | AWS account configuration |
| OpenShift Pull Secret | All cluster deployments | https://console.redhat.com/openshift/create/local |
| Offline Token | SNO Deploy | https://cloud.redhat.com/openshift/token |
| SSH Keys | All components | Generate with `ssh-keygen` |
| CI Token | CI builds | https://console-openshift-console.apps.ci.l2s4.p1.openshiftapps.com |
| RHEL Subscription | EC2/hypervisor hosts | Red Hat Subscription Manager |

---

## Daily Report Validation

The `edge-ic` plugin provides tools for validating daily report format before posting to Slack.

### Daily Report Format Rules

When generating daily reports for Slack:

1. **Include a header line** (e.g., "Daily Report:") at the top for proper `/copy` command alignment
2. **Use correct emoji format**:
   - `:done-circle-check:` for completed items
   - `:in-progress:` for in-progress items
   - `:jira-blocker:` for blocked items
3. **Consolidate similar bullets** - Group related items together to keep reports concise
4. **Use concise descriptions** - Be brief and direct
5. **Include Jira tickets** with format: `OCPEDGE-123: Description (https://redhat.atlassian.net/browse/OCPEDGE-123)`
6. **Render as plain text** - No code blocks, ready for direct copying

### Validation Script

Before posting daily reports to Slack, validate format:

```bash
plugins/edge-ic/bin/validate-daily-report.sh my-report.txt
```

See `plugins/edge-ic/references/validation-README.md` for complete validation documentation.

---

## Maintaining This Documentation

### Automatic Submodule Update Detection

A Claude Code hook checks whether git submodules (e.g., `two-node-toolbox/`) are behind their remote tracking branch at session start. If a submodule is stale, Claude will report how many commits it is behind and offer to update it.

**Hook location:** `.claude/hooks/update-submodules.sh`

**Behavior:**

1. Silently initializes any uninitialized submodules
2. Fetches from each submodule's remote and compares the pinned commit to the remote branch tip
3. If any submodules are behind, Claude reports the details and asks if you'd like to update
4. If you accept, Claude runs `git submodule update --remote <path>`, stages the change, and commits

The hook resolves each submodule's tracking branch in order: `.gitmodules` branch config, `origin/HEAD`, `main`, `master`. It exits silently if offline or if no `.gitmodules` file exists.

### Automatic New Tool Detection

This repository includes a Claude Code hook that automatically detects new tool directories at session start. When a new tool directory is added (a directory with a Makefile or README.md), Claude will:

1. Detect the undocumented tool
2. Notify the user
3. Offer to update this CLAUDE.md file

**Hook location:** `.claude/hooks/detect-new-tools.sh`

**When adding a new tool**, update the `DOCUMENTED_TOOLS` array in the hook script:

```bash
DOCUMENTED_TOOLS=(
    "two-node-toolbox"
    "ec2-deploy"
    "sno-deploy"
    "environments/lvm-operator"
    "your-new-tool"  # Add new tools here
)
```

---

## Additional Resources

For detailed component-specific guidance, see:

- `two-node-toolbox/CLAUDE.md` - Full development guidelines, coding standards, architecture details
- `environments/lvm-operator/CLAUDE.md` - LVM Operator workspace navigation, Konflux build chain
- Component README files in each directory
