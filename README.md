# Edge Tooling

Automation and development tools for deploying and testing OpenShift clusters in edge configurations — two-node HA, single-node (SNO), and related infrastructure.

## What's in here

| Directory | What it does |
|-----------|-------------|
| [two-node-toolbox/](two-node-toolbox/) | Deploy two-node OpenShift clusters (arbiter/fencing topologies) |
| [ec2-deploy/](ec2-deploy/) | Spin up EC2 instances for development and hypervisor use |
| [sno-deploy/](sno-deploy/) | Deploy Single Node OpenShift with DU configuration |
| [payload-monitor/](payload-monitor/) | Monitor nightly payload health for edge topologies |
| [environments/lvm-operator/](environments/lvm-operator/) | Development workspace for the LVM Storage operator |
| [plugins/](plugins/) | Claude Code plugin marketplace for OpenShift/edge workflows |
| [multi-repo-development/](multi-repo-development/) | Multi-repo development environment for cross-project work |

## Getting started

Each component has its own README with prerequisites, setup, and usage. Start with the one that matches your use case.

For a common end-to-end flow (EC2 instance → two-node cluster), see the [workflow guide](docs/claude/workflows.md).

## Contributing

PRs use the fork model. See [CLAUDE.md](CLAUDE.md) for project conventions.
