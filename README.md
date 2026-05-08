# Edge Tooling

Automation, AI skills, and deployment tools for OpenShift edge engineering — covering cluster deployments, CI monitoring, release workflows, and developer productivity through Claude Code plugins.

## What's in here

### Claude Code Plugins

Installable via `/plugin marketplace add openshift-eng/edge-tooling`.

| Plugin | What it does |
|--------|-------------|
| [edge-ocp-ci](plugins/edge-ocp-ci/) | Monitor nightly payload health across edge topologies with AI-enriched analysis |
| [edge-scrum](plugins/edge-scrum/) | Scrum process management — refinement, sprint planning, standups |
| [edge-ic](plugins/edge-ic/) | IC workflow automation — TODOs, status reports, Jira updates |
| [pr-review](plugins/pr-review/) | Post-review utilities for processing PR feedback |
| [lvms](plugins/lvms/) | LVMS release, QE, and operational workflows |
| [two-node](plugins/two-node/) | Two-node topology workflow automation |
| [challenge](plugins/challenge/) | Adversarial hypothesis reviewer for root cause analysis |
| [threat-model](plugins/threat-model/) | Security threat analysis for OpenShift PRs |
| [microshift-ci](plugins/microshift-ci/) | MicroShift CI failure analysis and JIRA bug creation |
| [microshift-release](plugins/microshift-release/) | MicroShift release testing automation |

### Deployment Tools

| Directory | What it does |
|-----------|-------------|
| [two-node-toolbox/](two-node-toolbox/) | Deploy two-node OpenShift clusters (arbiter/fencing topologies) |
| [ec2-deploy/](ec2-deploy/) | Spin up EC2 instances for development and hypervisor use |
| [sno-deploy/](sno-deploy/) | Deploy Single Node OpenShift with DU configuration |
| [payload-monitor/](payload-monitor/) | Nightly payload health monitoring for edge topologies |
| [environments/lvm-operator/](environments/lvm-operator/) | Development workspace for the LVM Storage operator |
| [multi-repo-development/](multi-repo-development/) | Multi-repo development environment for cross-project work |

## Getting started

Each component has its own README with prerequisites, setup, and usage. Start with the one that matches your use case.

For deployment walkthroughs (EC2 instance → two-node cluster), see the [workflow guide](docs/claude/workflows.md).

## Contributing

PRs use the fork model. See [CLAUDE.md](CLAUDE.md) for project conventions.
